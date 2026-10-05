"""Generate docs/images from the real cascade code (simulated sensor data, rules only).

    cd agent && python ../benchmarks/make_figures.py
"""
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from cascade import make_cascade
from models import Action, Reading

random.seed(7)
decide = make_cascade()  # no models configured: local hard limit + rules

temps, actions = [], []
t = 42.0
for i in range(120):
    # heats up for 80 readings (fault developing), then cools down
    t += random.uniform(-0.5, 2.0) if i < 80 else random.uniform(-3.0, 0.5)
    t = max(35.0, t)
    r = Reading(device_id="sim", temperature_c=round(t, 1), rssi=-55, free_heap=120_000)
    temps.append(r.temperature_c)
    actions.append(decide(r).action)

colors = {Action.ignore: "#94a3b8", Action.log: "#38bdf8",
          Action.alert: "#fbbf24", Action.shutdown: "#ef4444"}
fig, ax = plt.subplots(figsize=(9, 3.6))
ax.plot(temps, color="#334155", lw=1.2, zorder=1)
for a in Action:
    xs = [i for i, x in enumerate(actions) if x == a]
    ax.scatter(xs, [temps[i] for i in xs], s=18, color=colors[a], label=a.value, zorder=2)
for y, lbl in ((60, "log ≥ 60"), (75, "alert ≥ 75"), (90, "shutdown ≥ 90 (local hard limit)")):
    ax.axhline(y, color="#cbd5e1", lw=0.8, ls="--")
    ax.text(0, y + 0.6, lbl, fontsize=7, color="#64748b")
ax.set_xlabel("reading #"); ax.set_ylabel("chip temperature (°C)")
ax.set_title("Simulated temperature ramp: action chosen per reading (rules-only cascade)",
             fontsize=10)
ax.legend(ncol=4, fontsize=8, frameon=False, loc="upper left", bbox_to_anchor=(0, -0.2))
fig.tight_layout()
out = ROOT / "docs/images/decision_ramp.png"
fig.savefig(out, dpi=160)
print("wrote", out, {a.value: actions.count(a) for a in Action})
