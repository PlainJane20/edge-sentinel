"""Governed actions.

Risk is set per operation from this table, never from model output. Unknown
operations are denied. Safe-state actions (turning things off) run
automatically; re-energizing requires a second person's approval, which expires.
"""
from __future__ import annotations

import sqlite3
import time
import uuid
from enum import Enum
from pathlib import Path

from models import Action


class Tier(str, Enum):
    auto = "auto"
    approval = "approval"
    deny = "deny"


ACTION_TIERS = {
    Action.ignore: Tier.auto,
    Action.log: Tier.auto,
    Action.alert: Tier.auto,
    Action.shutdown: Tier.auto,  # safe-state: cutting power is always allowed
}

OPERATOR_COMMANDS = {
    "reenergize": Tier.approval,  # returning to a hazardous state needs sign-off
}

APPROVAL_TTL_S = 300


def tier_for_action(action: Action) -> Tier:
    return ACTION_TIERS.get(action, Tier.deny)


def tier_for_command(op: str) -> Tier:
    return OPERATOR_COMMANDS.get(op, Tier.deny)


class ApprovalError(Exception):
    pass


class ApprovalStore:
    """SQLite-backed so pending approvals survive a restart."""

    def __init__(self, path: str | Path, ttl_s: int = APPROVAL_TTL_S, clock=time.time):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.ttl_s, self.clock = ttl_s, clock
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS approvals (id TEXT PRIMARY KEY, op TEXT, "
            "device_id TEXT, requester TEXT, approver TEXT, created REAL, "
            "status TEXT)"
        )
        self.db.commit()

    def request(self, op: str, device_id: str, requester: str) -> str:
        if tier_for_command(op) is not Tier.approval:
            raise ApprovalError(f"operation {op!r} is not an approvable command")
        rid = uuid.uuid4().hex[:12]
        self.db.execute(
            "INSERT INTO approvals VALUES (?,?,?,?,?,?,?)",
            (rid, op, device_id, requester, None, self.clock(), "pending"),
        )
        self.db.commit()
        return rid

    def _row(self, rid: str):
        row = self.db.execute(
            "SELECT op, device_id, requester, approver, created, status "
            "FROM approvals WHERE id=?", (rid,)
        ).fetchone()
        if not row:
            raise ApprovalError("unknown approval id")
        return row

    def _expired(self, created: float) -> bool:
        return self.clock() - created > self.ttl_s

    def approve(self, rid: str, approver: str) -> None:
        op, dev, requester, _, created, status = self._row(rid)
        if status != "pending":
            raise ApprovalError(f"approval is {status}")
        if self._expired(created):
            raise ApprovalError("approval expired")
        if approver == requester:
            raise ApprovalError("requester cannot approve their own request")
        self.db.execute("UPDATE approvals SET approver=?, status='approved' WHERE id=?",
                        (approver, rid))
        self.db.commit()

    def consume(self, rid: str) -> dict:
        """One-time use: marks the approval executed and returns its details."""
        op, dev, requester, approver, created, status = self._row(rid)
        if status != "approved":
            raise ApprovalError(f"approval is {status}, not approved")
        if self._expired(created):
            raise ApprovalError("approval expired")
        self.db.execute("UPDATE approvals SET status='executed' WHERE id=?", (rid,))
        self.db.commit()
        return {"op": op, "device_id": dev, "requester": requester, "approver": approver}
