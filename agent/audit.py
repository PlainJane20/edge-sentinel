"""Hash-chained append-only audit log (JSONL).

Each record stores the SHA-256 of the previous record, so editing or deleting
a line breaks verification from that point on. This detects tampering; it does
not prevent it (anyone with file access can rewrite the whole chain).
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path

GENESIS = "0" * 64


class AuditLog:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._last = self._load_last_hash()

    def _load_last_hash(self) -> str:
        last = GENESIS
        if self.path.exists():
            for line in self.path.read_text().splitlines():
                if line.strip():
                    last = json.loads(line)["hash"]
        return last

    @staticmethod
    def _digest(prev: str, body: dict) -> str:
        payload = json.dumps(body, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256((prev + payload).encode()).hexdigest()

    def append(self, event: str, data: dict) -> dict:
        with self._lock:
            body = {"ts": time.time(), "event": event, "data": data}
            h = self._digest(self._last, body)
            record = {**body, "prev": self._last, "hash": h}
            with self.path.open("a") as f:
                f.write(json.dumps(record, sort_keys=True) + "\n")
            self._last = h
            return record

    def records(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(l) for l in self.path.read_text().splitlines() if l.strip()]

    def verify(self) -> tuple[bool, int | None]:
        """Return (ok, index of first bad record)."""
        prev = GENESIS
        for i, rec in enumerate(self.records()):
            body = {k: rec[k] for k in ("ts", "event", "data")}
            if rec["prev"] != prev or rec["hash"] != self._digest(prev, body):
                return False, i
            prev = rec["hash"]
        return True, None
