import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app
from audit import AuditLog
from auth import AuthConfig
from cascade import make_cascade
from policy import ApprovalError, ApprovalStore


def test_audit_chain_detects_tampering(tmp_path):
    log = AuditLog(tmp_path / "a.jsonl")
    for i in range(3):
        log.append("e", {"i": i})
    assert log.verify() == (True, None)

    lines = (tmp_path / "a.jsonl").read_text().splitlines()
    lines[1] = lines[1].replace('"i": 1', '"i": 99').replace('"i":1', '"i":99')
    (tmp_path / "a.jsonl").write_text("\n".join(lines) + "\n")
    assert AuditLog(tmp_path / "a.jsonl").verify() == (False, 1)


def test_audit_chain_survives_restart(tmp_path):
    AuditLog(tmp_path / "a.jsonl").append("e", {})
    log2 = AuditLog(tmp_path / "a.jsonl")
    log2.append("e", {})
    assert log2.verify() == (True, None)


def make_store(tmp_path, now):
    return ApprovalStore(tmp_path / "ap.db", ttl_s=60, clock=lambda: now[0])


def test_self_approval_blocked(tmp_path):
    s = make_store(tmp_path, [0])
    rid = s.request("reenergize", "dev1", "alice")
    with pytest.raises(ApprovalError, match="own request"):
        s.approve(rid, "alice")


def test_unknown_command_denied(tmp_path):
    with pytest.raises(ApprovalError):
        make_store(tmp_path, [0]).request("format_disk", "dev1", "alice")


def test_approval_expires(tmp_path):
    now = [0]
    s = make_store(tmp_path, now)
    rid = s.request("reenergize", "dev1", "alice")
    s.approve(rid, "bob")
    now[0] = 61
    with pytest.raises(ApprovalError, match="expired"):
        s.consume(rid)


def test_approval_is_single_use_and_persistent(tmp_path):
    s = make_store(tmp_path, [0])
    rid = s.request("reenergize", "dev1", "alice")
    s2 = make_store(tmp_path, [0])  # simulates restart
    s2.approve(rid, "bob")
    assert s2.consume(rid)["approver"] == "bob"
    with pytest.raises(ApprovalError):
        s2.consume(rid)


def test_execute_requires_approval(tmp_path):
    s = make_store(tmp_path, [0])
    rid = s.request("reenergize", "dev1", "alice")
    with pytest.raises(ApprovalError, match="not approved"):
        s.consume(rid)


def test_api_flow_and_audit(tmp_path):
    app = create_app(make_cascade(), AuditLog(tmp_path / "a.jsonl"),
                     ApprovalStore(tmp_path / "ap.db"), AuthConfig())
    c = TestClient(app)
    d = c.post("/readings", json={"device_id": "d", "temperature_c": 95}).json()
    assert d["action"] == "shutdown"

    rid = c.post("/commands", json={"op": "reenergize", "device_id": "d"},
                   headers={"X-Operator": "alice"}).json()["id"]
    assert c.post(f"/commands/{rid}/execute").status_code == 409
    alice, bob = {"X-Operator": "alice"}, {"X-Operator": "bob"}
    assert c.post(f"/approvals/{rid}/approve", headers=alice).status_code == 409
    assert c.post(f"/approvals/{rid}/approve", headers=bob).status_code == 200
    assert c.post(f"/commands/{rid}/execute", headers=bob).status_code == 200
    assert c.get("/audit/verify").json()["ok"] is True
    assert len(c.get("/history").json()) == 1
