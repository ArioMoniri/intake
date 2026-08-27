# ADR-023 · RED carries three axes: route × register × location

Status: Accepted

## Context

Alarm is a mechanism of harm for some REDs (a child with stridor deteriorates when distressed; a safeguarding RED read aloud in the wrong room undoes the safeguard), and telling a checked-in patient to call 112 can send them out of the building that could treat them. One-axis RED delivery is therefore itself a hazard.

## Decision

Every RED rule declares route (EMERGENCY_NOW | SAME_DAY_ACIL | EXPEDITE), register (ALERT | CALM | SILENT | DEFERRED_CLINICIAN) and resolves its action for location (REMOTE | ON_SITE | UNKNOWN). register and location are required fields with no default permitted; the compiler rejects a rule that omits a register or whose action does not resolve for all three locations; under ON_SITE the 112 affordance is absent, not de-emphasised.

## Consequences

Invariant 21 and the red_axes_completeness safety suite; the RED script is pre-positioned on-device and triggered over the data channel (D12), and the preemption test asserts the RED path touches no media transport.
