"""Time the gateway's own work: cascade + audit append, in-process.

This excludes Wi-Fi, HTTP and any model call, so it is a floor, not an
end-to-end number. Re-run with models configured and over a real network to
fill in the rest of docs/SLA_AND_LATENCY_BUDGET.md.

    cd agent && python ../benchmarks/latency_probe.py
"""
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

from audit import AuditLog
from cascade import make_cascade
from models import Reading

N = 2000
decide = make_cascade()
with tempfile.TemporaryDirectory() as d:
    log = AuditLog(Path(d) / "a.jsonl")
    cascade_ms, append_ms = [], []
    for i in range(N):
        r = Reading(device_id="sim", temperature_c=40 + (i % 60), rssi=-55, free_heap=120_000)
        t0 = time.perf_counter(); dec = decide(r); t1 = time.perf_counter()
        log.append("decision", {"reading": r.model_dump(), "decision": dec.model_dump()})
        t2 = time.perf_counter()
        cascade_ms.append((t1 - t0) * 1000); append_ms.append((t2 - t1) * 1000)

def p(xs, q):
    return sorted(xs)[min(len(xs) - 1, int(len(xs) * q))]

print(f"n={N}")
for name, xs in (("cascade (rules)", cascade_ms), ("audit append", append_ms)):
    print(f"{name:<16} p50={statistics.median(xs):.3f} ms  p95={p(xs,.95):.3f} ms  p99={p(xs,.99):.3f} ms")
