"""Gateway: ingest ESP32 readings, decide, govern, audit."""
from __future__ import annotations

import logging
import os

from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict

from audit import AuditLog
from auth import AuthConfig, make_dependencies
from cascade import build_default
from models import Decision, Reading
from policy import ApprovalError, ApprovalStore, Tier, tier_for_action

log = logging.getLogger("edge-sentinel")
logging.basicConfig(level=logging.INFO)

DATA_DIR = os.getenv("EDGE_DATA_DIR", "data")


DASHBOARD = Path(__file__).parent / "static" / "dashboard.html"


class CommandRequest(BaseModel):
    # Identity comes from the bearer token. Unknown fields (e.g. `requester`)
    # are rejected with 422 so nobody believes a body-supplied name is used.
    model_config = ConfigDict(extra="forbid")
    op: str
    device_id: str


def create_app(decide=None, audit: AuditLog | None = None,
               approvals: ApprovalStore | None = None,
               auth: AuthConfig | None = None) -> FastAPI:
    app = FastAPI(title="Edge Sentinel")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","),
        allow_methods=["*"], allow_headers=["*"],
    )
    decide = decide or build_default()
    audit = audit or AuditLog(f"{DATA_DIR}/audit.jsonl")
    approvals = approvals or ApprovalStore(f"{DATA_DIR}/approvals.db")
    auth = auth or AuthConfig.from_env()
    auth.warn_if_disabled()
    require_device, require_operator = make_dependencies(auth)

    @app.post("/readings", response_model=Decision)
    def ingest(reading: Reading, _dev: str = Depends(require_device)) -> Decision:
        decision = decide(reading)
        tier = tier_for_action(decision.action)
        if tier is Tier.deny:  # defensive: unknown actions never execute
            raise HTTPException(403, f"action {decision.action} denied by policy")
        audit.append("decision", {
            "reading": reading.model_dump(),
            "decision": decision.model_dump(),
            "tier": tier.value,
        })
        return decision

    @app.get("/history")
    def history(limit: int = 200, _op: str = Depends(require_operator)) -> list[dict]:
        recs = [r for r in audit.records() if r["event"] == "decision"]
        return [{"ts": r["ts"], **r["data"]} for r in recs[-limit:]]

    @app.get("/audit/verify")
    def verify(_op: str = Depends(require_operator)) -> dict:
        ok, bad = audit.verify()
        return {"ok": ok, "first_bad_index": bad}

    @app.post("/commands")
    def request_command(req: CommandRequest,
                        requester: str = Depends(require_operator)) -> dict:
        evidence = {**req.model_dump(), "requester": requester}
        try:
            rid = approvals.request(req.op, req.device_id, requester)
        except ApprovalError as e:
            audit.append("command_denied", {**evidence, "reason": str(e)})
            raise HTTPException(403, str(e))
        audit.append("command_requested", {**evidence, "id": rid})
        return {"id": rid, "status": "pending", "requester": requester}

    @app.post("/approvals/{rid}/approve")
    def approve(rid: str, approver: str = Depends(require_operator)) -> dict:
        try:
            approvals.approve(rid, approver)
        except ApprovalError as e:
            audit.append("approval_rejected", {"id": rid, "approver": approver,
                                               "reason": str(e)})
            raise HTTPException(409, str(e))
        audit.append("command_approved", {"id": rid, "approver": approver})
        return {"id": rid, "status": "approved", "approver": approver}

    @app.post("/commands/{rid}/execute")
    def execute(rid: str, executor: str = Depends(require_operator)) -> dict:
        try:
            cmd = approvals.consume(rid)
        except ApprovalError as e:
            audit.append("execute_rejected", {"id": rid, "executor": executor,
                                              "reason": str(e)})
            raise HTTPException(409, str(e))
        # Relay publish to the device would happen here (not implemented yet).
        audit.append("command_executed", {"id": rid, **cmd, "executor": executor})
        return {"id": rid, "status": "executed", **cmd, "executor": executor}

    @app.get("/dashboard", include_in_schema=False)
    def dashboard() -> FileResponse:
        # The HTML is static and carries no data; its API calls need tokens.
        return FileResponse(DASHBOARD, media_type="text/html")

    @app.get("/healthz")
    def healthz() -> dict:
        return {"ok": True, "auth": auth.enabled}

    return app


app = create_app()
