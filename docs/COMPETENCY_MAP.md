# Competency map

Each entry names the code or test that demonstrates it. Nothing here is claimed without evidence in the repository.

## Systems design under uncertainty

**Behavior:** Decide what happens when model layers are slow, wrong, or down.

**Evidence:**
- `cascade.py` degrades to rules on any model failure; `test_jev_exception_falls_back_to_rules`.
- Low or missing confidence escalates rather than acting; `test_missing_confidence_escalates`.
- Critical readings are decided locally with no model call; `test_hard_limit_skips_models`.

## Risk and governance

**Behavior:** Turn policy into enforced controls rather than documentation.

**Evidence:**
- Risk tiers come from a fixed table and unknown operations are denied (`policy.py`).
- Approvals are single-use, expire, and cannot be self-granted; `test_self_approval_blocked`, `test_approval_expires`, `test_approval_is_single_use_and_persistent`.
- Execution requires a prior approval; `test_execute_requires_approval`.

## Auditability

**Behavior:** Make decisions reviewable after the fact.

**Evidence:**
- Every decision stores the triggering reading, the source and the confidence.
- The hash chain detects edits and survives restarts; `test_audit_chain_detects_tampering`, `test_audit_chain_survives_restart`.

## Hardware and embedded integration

**Behavior:** Connect a microcontroller to a service with a defined contract.

**Evidence:**
- `firmware/` reports sensor state over Wi-Fi using values from the interface contract.
- `INTERFACE_CONTROL_DOC.md` defines the payloads both sides must honor.
- **Not yet demonstrated:** firmware has not been compiled or flashed on a board.

## Measurement discipline

**Behavior:** Report only what was measured, and say what the number excludes.

**Evidence:**
- `SLA_AND_LATENCY_BUDGET.md` lists unmeasured hops as unmeasured.
- `benchmarks/latency_probe.py` states what its numbers leave out.
