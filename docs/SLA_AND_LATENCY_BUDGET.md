# Latency budget

Targets are design budgets, not results. The measured column is filled in only where a number exists.

| Hop | Budget (design target) | Measured | How |
|---|---|---|---|
| Sensor read on ESP32 | not set | not measured | needs hardware |
| ESP32 to gateway (Wi-Fi + HTTP) | not set | not measured | needs hardware |
| Cascade, rules path | 5 ms | p50 0.001 ms, p95 0.002 ms | `benchmarks/latency_probe.py`, in-process |
| Audit append | 5 ms | p50 0.063 ms, p95 0.108 ms | `benchmarks/latency_probe.py`, in-process |
| Jev call | not set | p50 125 ms, p95 167 ms (48 calls) | `benchmarks/sensor_eval.py`, sequential, from a laptop over the internet, so it includes network |
| LLM escalation | not set | not measured | needs `ANTHROPIC_API_KEY` |
| Gateway to device (command) | not set | not implemented | |

**In-process rows** (cascade, audit append): Apple M4 Pro, Python 3.14, 2,000 readings. These exclude the network, HTTP parsing and any model call, so they are a floor, not an end-to-end figure.

**Jev row:** 48 sequential calls on 2026-10-05 from a laptop over the public internet. It depends on my network and TypeSafe's load that day, and says nothing about p99 or concurrency.

## Safety does not depend on this budget

If the gateway is slow or unreachable, the device must fall back to the threshold compiled into its firmware. The cascade also applies a hard limit locally before any model is consulted. Latency affects how early an anomaly is flagged; it should never be the thing that stops a shutdown.

## Next

1. Flash a board and measure the Wi-Fi + HTTP hop.
2. Add Jev and LLM timings with the same probe.
3. Model the hops as a critical path with slack per hop, as in `critical-path-radar`.
