"""Offline tests for token authentication (no network, no models)."""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app
from audit import AuditLog
from auth import AuthConfig
from cascade import make_cascade
from policy import ApprovalStore

READING = {"device_id": "d", "temperature_c": 50}
CMD = {"op": "reenergize", "device_id": "d"}


def build(tmp_path, auth):
    audit = AuditLog(tmp_path / "a.jsonl")
    app = create_app(make_cascade(), audit, ApprovalStore(tmp_path / "ap.db"), auth)
    return TestClient(app), audit


def bearer(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture
def secured(tmp_path):
    cfg = AuthConfig.from_env({"EDGE_DEVICE_TOKENS": "dev1,dev2",
                               "EDGE_OPERATOR_TOKENS": "alice:tokA,bob:tokB"})
    return build(tmp_path, cfg)


# -- config parsing ---------------------------------------------------------
def test_config_parsing():
    cfg = AuthConfig.from_env({"EDGE_DEVICE_TOKENS": " a , b ,",
                               "EDGE_OPERATOR_TOKENS": "alice:x, bob:y"})
    assert cfg.device_tokens == ("a", "b")
    assert cfg.operator_tokens == {"x": "alice", "y": "bob"}
    assert cfg.enabled and not AuthConfig.from_env({}).enabled


@pytest.mark.parametrize("bad", ["alice", "alice:", ":tok", "alice:a,bob"])
def test_bad_operator_config_fails_loudly(bad):
    with pytest.raises(ValueError):
        AuthConfig.from_env({"EDGE_OPERATOR_TOKENS": bad})


# -- disabled mode ----------------------------------------------------------
def test_disabled_mode_open_and_reported(tmp_path, caplog):
    with caplog.at_level("WARNING", logger="edge-sentinel"):
        c, _ = build(tmp_path, AuthConfig())
    assert "AUTHENTICATION IS DISABLED" in caplog.text
    assert c.get("/healthz").json() == {"ok": True, "auth": False}
    assert c.post("/readings", json=READING).status_code == 200
    assert c.get("/history").status_code == 200
    assert c.get("/audit/verify").status_code == 200
    assert c.post("/commands", json=CMD).json()["requester"] == "anonymous"


def test_disabled_mode_demo_identity_header_enforces_self_approval(tmp_path):
    c, _ = build(tmp_path, AuthConfig())
    rid = c.post("/commands", json=CMD, headers={"X-Operator": "alice"}).json()["id"]
    assert c.post(f"/approvals/{rid}/approve", headers={"X-Operator": "alice"}).status_code == 409
    assert c.post(f"/approvals/{rid}/approve", headers={"X-Operator": "bob"}).status_code == 200


def test_enabled_healthz_reports_auth_and_needs_no_token(secured):
    c, _ = secured
    assert c.get("/healthz").json() == {"ok": True, "auth": True}


# -- device token -----------------------------------------------------------
def test_device_ingest_requires_token(secured):
    c, _ = secured
    assert c.post("/readings", json=READING).status_code == 401
    assert c.post("/readings", json=READING, headers=bearer("nope")).status_code == 401
    assert c.post("/readings", json=READING,
                  headers={"Authorization": "Basic dev1"}).status_code == 401
    assert c.post("/readings", json=READING, headers=bearer("dev1")).status_code == 200
    assert c.post("/readings", json=READING, headers=bearer("dev2")).status_code == 200


def test_rejected_ingest_is_not_audited(secured):
    c, audit = secured
    c.post("/readings", json=READING)
    assert audit.records() == []


def test_role_separation_403(secured):
    c, _ = secured
    assert c.post("/readings", json=READING, headers=bearer("tokA")).status_code == 403
    for method, path in [("get", "/history"), ("get", "/audit/verify"),
                         ("post", "/commands")]:
        r = getattr(c, method)(path, headers=bearer("dev1"),
                               **({"json": CMD} if method == "post" else {}))
        assert r.status_code == 403, path


# -- operator endpoints -----------------------------------------------------
def test_operator_endpoints_require_token(secured):
    c, _ = secured
    for method, path in [("get", "/history"), ("get", "/audit/verify"),
                         ("post", "/commands"), ("post", "/approvals/x/approve"),
                         ("post", "/commands/x/execute")]:
        kw = {"json": CMD} if path == "/commands" else {}
        assert getattr(c, method)(path, **kw).status_code == 401, path
        assert getattr(c, method)(path, headers=bearer("wrong"), **kw).status_code == 401, path
    assert c.get("/history", headers=bearer("tokA")).status_code == 200
    assert c.get("/audit/verify", headers=bearer("tokB")).json()["ok"] is True


def test_self_approval_blocked_by_token_identity(secured):
    c, _ = secured
    rid = c.post("/commands", json=CMD, headers=bearer("tokA")).json()["id"]
    r = c.post(f"/approvals/{rid}/approve", headers=bearer("tokA"))
    assert r.status_code == 409 and "own request" in r.json()["detail"]
    assert c.post(f"/approvals/{rid}/approve", headers=bearer("tokB")).status_code == 200


def test_body_supplied_identity_is_rejected(secured):
    c, _ = secured
    r = c.post("/commands", json={**CMD, "requester": "carol"}, headers=bearer("tokA"))
    assert r.status_code == 422


def test_body_approver_cannot_bypass_self_approval(secured):
    c, _ = secured
    rid = c.post("/commands", json=CMD, headers=bearer("tokA")).json()["id"]
    # alice tries to claim she is bob in the body: ignored, she is still alice
    r = c.post(f"/approvals/{rid}/approve", json={"approver": "bob"}, headers=bearer("tokA"))
    assert r.status_code == 409
    # and execute still refuses because nothing was approved
    assert c.post(f"/commands/{rid}/execute", headers=bearer("tokA")).status_code == 409


def test_audit_records_authenticated_identities(secured):
    c, audit = secured
    rid = c.post("/commands", json=CMD, headers=bearer("tokA")).json()["id"]
    c.post(f"/approvals/{rid}/approve", headers=bearer("tokA"))  # rejected
    c.post(f"/approvals/{rid}/approve", headers=bearer("tokB"))
    c.post(f"/commands/{rid}/execute", headers=bearer("tokA"))
    by_event = {r["event"]: r["data"] for r in audit.records()}
    assert by_event["command_requested"]["requester"] == "alice"
    assert by_event["approval_rejected"]["approver"] == "alice"
    assert by_event["command_approved"]["approver"] == "bob"
    assert by_event["command_executed"]["executor"] == "alice"
    assert by_event["command_executed"]["approver"] == "bob"
    assert audit.verify() == (True, None)


def test_failed_auth_does_not_reveal_which_part_failed(secured):
    c, _ = secured
    a = c.get("/history", headers=bearer("tokA-typo"))
    b = c.get("/history", headers=bearer(""))
    assert a.status_code == b.status_code == 401
    assert a.headers["www-authenticate"] == "Bearer"


def test_env_tokens_used_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("EDGE_DEVICE_TOKENS", "envdev")
    monkeypatch.setenv("EDGE_OPERATOR_TOKENS", "zed:envop")
    app = create_app(make_cascade(), AuditLog(tmp_path / "a.jsonl"),
                     ApprovalStore(tmp_path / "ap.db"))
    c = TestClient(app)
    assert c.post("/readings", json=READING, headers=bearer("envdev")).status_code == 200
    assert c.post("/commands", json=CMD, headers=bearer("envop")).json()["requester"] == "zed"
    assert c.post("/commands", json=CMD).status_code == 401
