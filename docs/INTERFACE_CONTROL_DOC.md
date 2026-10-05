# Interface control document

The contract between the firmware and the gateway. Change both sides together.

## Device to gateway (HTTP, current)

`POST /readings`

```json
{
  "device_id": "AA:BB:CC:DD:EE:FF",
  "temperature_c": 63.2,
  "rssi": -61,
  "uptime_s": 1204,
  "free_heap": 182340
}
```

Response (`Decision`):

```json
{
  "action": "log",
  "anomalous": false,
  "source": "jev",
  "confidence": 0.93,
  "escalated": false
}
```

| Field | Values |
|---|---|
| `action` | `ignore`, `log`, `alert`, `shutdown` |
| `source` | `local-rule`, `jev`, `llm`, `rules-fallback` |
| `confidence` | 0 to 1, or `null` when no model decided |

The device must treat a missing or failed response as "no decision" and apply its own local threshold.

## Operator commands

| Endpoint | Purpose |
|---|---|
| `POST /commands` `{op, device_id, requester}` | Request an approvable command (only `reenergize` exists) |
| `POST /approvals/{id}/approve` `{approver}` | Approve; the requester cannot approve their own request |
| `POST /commands/{id}/execute` | Consume an approved request once, before it expires (300 s) |
| `GET /history?limit=` | Recent decisions with the readings that triggered them |
| `GET /audit/verify` | Check the hash chain; returns the first bad record index |

## Planned

- MQTT transport (`sentinel/<device_id>/telemetry`, `sentinel/<device_id>/command`) to replace HTTP polling
- Command delivery to the relay on the device (execute currently only records the event)
- Authentication for operators and devices
