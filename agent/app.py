"""Gateway: ingest ESP32 readings, decide, govern, audit."""
from __future__ import annotations

import logging
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from audit import AuditLog
from cascade import build_default
from models import Decision, Reading
from policy import ApprovalError, ApprovalStore, Tier, tier_for_action

log = logging.getLogger("edge-sentinel")
logging.basicConfig(level=logging.INFO)

DATA_DIR = os.getenv("EDGE_DATA_DIR", "data")


class CommandRequest(BaseModel):
    op: str
    device_id: str
    requester: str


class ApproveRequest(BaseModel):
    approver: str


def create_app(decide=None, audit: AuditLog | None = None,
               approvals: ApprovalStore | None = None) -> FastAPI:
    app = FastAPI(title="Edge Sentinel")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","),
        allow_methods=["*"], allow_headers=["*"],
    )
    decide = decide or build_default()
    audit = audit or AuditLog(f"{DATA_DIR}/audit.jsonl")
    approvals = approvals or ApprovalStore(f"{DATA_DIR}/approvals.db")

    @app.post("/readings", response_model=Decision)
    def ingest(reading: Reading) -> Decision:
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
    def history(limit: int = 200) -> list[dict]:
        recs = [r for r in audit.records() if r["event"] == "decision"]
        return [{"ts": r["ts"], **r["data"]} for r in recs[-limit:]]

    @app.get("/audit/verify")
    def verify() -> dict:
        ok, bad = audit.verify()
        return {"ok": ok, "first_bad_index": bad}

    @app.post("/commands")
    def request_command(req: CommandRequest) -> dict:
        try:
            rid = approvals.request(req.op, req.device_id, req.requester)
        except ApprovalError as e:
            audit.append("command_denied", {**req.model_dump(), "reason": str(e)})
            raise HTTPException(403, str(e))
        audit.append("command_requested", {**req.model_dump(), "id": rid})
        return {"id": rid, "status": "pending"}

    @app.post("/approvals/{rid}/approve")
    def approve(rid: str, req: ApproveRequest) -> dict:
        try:
            approvals.approve(rid, req.approver)
        except ApprovalError as e:
            audit.append("approval_rejected", {"id": rid, "approver": req.approver,
                                               "reason": str(e)})
            raise HTTPException(409, str(e))
        audit.append("command_approved", {"id": rid, "approver": req.approver})
        return {"id": rid, "status": "approved"}

    @app.post("/commands/{rid}/execute")
    def execute(rid: str) -> dict:
        try:
            cmd = approvals.consume(rid)
        except ApprovalError as e:
            raise HTTPException(409, str(e))
        # Relay publish to the device would happen here (not implemented yet).
        audit.append("command_executed", {"id": rid, **cmd})
        return {"id": rid, "status": "executed", **cmd}

    @app.get("/healthz")
    def healthz() -> dict:
        return {"ok": True}

    return app


app = create_app()
