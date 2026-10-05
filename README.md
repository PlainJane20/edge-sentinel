# edge-sentinel

Governed agents that act on the physical world. An ESP32 streams telemetry to a
gateway. A decision cascade chooses an action (`ignore`, `log`, `alert`,
`shutdown`), and every action passes through a policy layer and a tamper-evident
audit log.

```
ESP32 --HTTP POST /readings--> agent (FastAPI)
                                 1. local hard limit   (no model, deterministic)
                                 2. Jev                (fast, typed, confidence)
                                 3. LLM                (only if Jev is unsure)
                                 4. rules              (if any model layer fails)
                                 -> policy tier -> hash-chained audit log
```

## What is built

- Decision cascade with confidence-based escalation (`agent/cascade.py`)
- Per-operation policy table; unknown operations denied; re-energize needs a
  second person's approval, single-use, with expiry (`agent/policy.py`)
- Hash-chained audit log with verification (`agent/audit.py`, `GET /audit/verify`)
- Persistent approvals (SQLite) and decision history
- ESP32 firmware that reports temperature, RSSI and heap (`firmware/`)
- Simulated device so it runs with no hardware (`agent/simulate.py`)
- 16 tests, runnable offline

## What is not done yet

- [ ] Firmware compiled and flashed on a real board
- [ ] Jev verified against the live API (confidence extraction is unverified)
- [ ] Relay command delivery to the device (the execute endpoint only logs)
- [ ] Measured latency per hop and a Jev vs LLM benchmark
- [ ] Dashboard for `/history`
- [ ] Docs: architecture, interface contract, latency budget

No performance numbers are claimed until they are measured.

## Run

```bash
cd agent
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m pytest
uvicorn app:app --reload          # terminal 1
python simulate.py                # terminal 2
```

Optional model layers:

```bash
pip install "pydantic-ai-slim[typesafe,anthropic]"
export TYPESAFE_API_KEY=...       # Jev
export ANTHROPIC_API_KEY=...      # LLM fallback
```

## Flash a real ESP32

```bash
export WIFI_SSID=... WIFI_PASS=... GATEWAY_URL=http://<laptop-ip>:8000
cd firmware && pio run -t upload && pio device monitor
```

Run the gateway with `--host 0.0.0.0` so the board can reach it.

## Known limits

The audit chain detects edits and deletions, but anyone with file access can
rewrite the whole chain. There is no authentication on the HTTP API yet; the
`requester` and `approver` fields are self-declared.
