"""Does Jev follow the written sensor policy, and how confident is it?

Labels come from cascade.rules(), the same policy that is written into Jev's
instructions. So this measures policy-following, not independent accuracy.
Readings at or above the shutdown limit are excluded: the cascade decides those
locally and never calls a model.

    cd agent && TYPESAFE_API_KEY=... python ../benchmarks/sensor_eval.py
"""
import itertools
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))

from cascade import TEMP_SHUTDOWN_C, build_jev, rules
from models import Reading

THRESHOLD = 0.8
temps = [30, 45, 58, 59, 60, 61, 70, 74, 75, 76, 85, 89]          # boundaries included
conds = [(-50, 150_000), (-90, 150_000), (-50, 10_000), (-90, 10_000)]  # (rssi, free_heap)
cases = [Reading(device_id="eval", temperature_c=t, rssi=r, free_heap=h)
         for t, (r, h) in itertools.product(temps, conds) if t < TEMP_SHUTDOWN_C]

jev = build_jev()
rows = []
for r in cases:
    t0 = time.perf_counter()
    action, conf = jev(r)
    ms = (time.perf_counter() - t0) * 1000
    rows.append({"temp": r.temperature_c, "rssi": r.rssi, "heap": r.free_heap,
                 "label": rules(r).value, "jev": action.value, "conf": conf, "ms": ms})

n = len(rows)
correct = [x for x in rows if x["jev"] == x["label"]]
confident = [x for x in rows if x["conf"] is not None and x["conf"] >= THRESHOLD]
conf_correct = [x for x in confident if x["jev"] == x["label"]]
escalated = n - len(confident)
ms = sorted(x["ms"] for x in rows)

print(f"cases={n}  threshold={THRESHOLD}")
print(f"agreement with policy:      {len(correct)}/{n} = {len(correct)/n:.0%}")
print(f"confident (>= {THRESHOLD}):          {len(confident)}/{n} = {len(confident)/n:.0%}")
print(f"  accuracy when confident:  {len(conf_correct)}/{len(confident)}" if confident else "  none confident")
print(f"escalated to fallback:      {escalated}/{n} = {escalated/n:.0%}")
wrong_conf = [x for x in confident if x["jev"] != x["label"]]
print(f"confident but wrong:        {len(wrong_conf)}")
print(f"latency p50={statistics.median(ms):.0f} ms  p95={ms[int(n*.95)]:.0f} ms  (sequential, includes network)")
print("\nmisses:")
for x in rows:
    if x["jev"] != x["label"]:
        print(f"  {x['temp']}C rssi={x['rssi']} heap={x['heap']}: label={x['label']} jev={x['jev']} conf={x['conf']:.2f}")
json.dump(rows, open(Path(__file__).with_name("sensor_eval_results.json"), "w"), indent=1)
