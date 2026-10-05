# ADR 001: The model proposes, policy decides

## Status
Accepted

## Context
Earlier projects in this portfolio gate agent actions with approvals, but a review found gaps: one let a model's own risk label decide whether an action needed approval, one let a requester approve their own action, and one recorded approvals that nothing ever checked before executing.

## Decision
- Models choose only among a fixed set of actions.
- Risk tier is looked up from a table keyed by operation, never read from model output.
- Unknown operations are denied.
- Turning something off is always allowed. Returning to a hazardous state needs a second person, and the approval expires and can be used once.
- Hard safety limits are applied before any model is consulted.

## Consequences
- A model that mislabels or hallucinates an action cannot widen its own permissions.
- Adding an operation requires editing the table, which is a reviewable change.
- The cost is rigidity: a genuinely new situation needs a code change, not a better prompt.
