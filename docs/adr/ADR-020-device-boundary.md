# ADR-020 · Medical-device boundary behind device_functions; Stage B CE Class IIb

Status: Accepted (amended — v1.4 said Class IIa; MDCG 2019-11 Annex IV names the depression-scoring case almost verbatim under Rule 11(a), and the failure mode to assess is the false negative)

## Context

Automated triage and automated instrument interpretation are MDSW under Tıbbi Cihaz Yönetmeliği Rule 11. Shipping them commercially before CE is unlawful; pretending they are not device functions is worse. Rule 11's test is counterfactual — harm is assessed against the consequence of the software being wrong.

## Decision

Device functions live behind the device_functions flag: off for commercial tenants until CE (no automated patient-facing triage advice, no automated severity interpretation; static 112 text at fixed points; red-flag answers shown to the clinician as patient-reported data; shadow triage logged); on only for investigation tenants bound to a recorded KAEK+TİTCK study id. Stage B targets Class IIb conformity, and the classification is confirmed by a written notified-body opinion before scope is fixed (HB-L10).

## Consequences

INT-117 is the gate with tests for both modes and for no leakage when off; INT-216 writes the boundary table; the intended-purpose wording is load-bearing (MDCG 2019-11 Rev.1 closed the NLP safe harbour by name). The ethics route is KAEK, never ATADEK (00 §0.4).
