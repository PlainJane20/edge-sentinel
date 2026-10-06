# Interface control document

The contract between the firmware and the gateway. Change both sides together.

## Authentication

Static bearer tokens read from the gateway's environment:

| Variable | Format | Grants |
|---|---|---|
| `EDGE_DEVICE_TOKENS` | `tok1,tok2` | `POST /readings` |
| `EDGE_OPERATOR_TOKENS` | `alice:tokA,bob:tokB` | every operator endpoint, `/history`, `/audit/verify`; the name becomes the identity |

Send `Authorization: Bearer <token>`. Tokens are compared with `hmac.compare_digest`.

| Status | Meaning |
|---|---|
| 401 | Missing, malformed or unknown token (`WWW-Authenticate: Bearer`) |
| 403 | Valid token of the wrong kind (device token on an operator endpoint, or the reverse), or policy denial |
| 409 | Authenticated, but the approval rules refused (self-approval, expired, reused, not approved) |
| 422 | Unknown body field, for example a `requester` or `approver` the caller tried to supply |

Requester, approver and executor identities come only from the token and are
written to the audit log. They are never read from the request body.

If both variables are unset, authentication is **disabled** (local demo): the
gateway logs a loud warning at startup and `GET /healthz` returns `"auth": false`.
In that mode the operator identity is the optional `X-Operator` header
(default `anonymous`), which is self-declared; use it only on a trusted machine.
`GET /healthz` and `GET /dashboard` (static HTML, no data) never need a token.

## Device to gateway (HTTP, current)

`POST /readings` (needs a device token when auth is enabled)

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
| `POST /commands` `{op, device_id}` | Request an approvable command (only `reenergize` exists); requester = token identity |
| `POST /approvals/{id}/approve` (no body) | Approve; the token identity cannot approve its own request |
| `POST /commands/{id}/execute` | Consume an approved request once, before it expires (300 s); executor is audited |
| `GET /history?limit=` | Recent decisions with the readings that triggered them |
| `GET /audit/verify` | Check the hash chain; returns the first bad record index |

All rows above need an operator token when auth is enabled.

## Planned

- MQTT transport (`sentinel/<device_id>/telemetry`, `sentinel/<device_id>/command`) to replace HTTP polling
- Command delivery to the relay on the device (execute currently only records the event)
- Token rotation, per-device tokens bound to a `device_id`, TLS, and a real identity provider (current tokens are static shared secrets)
