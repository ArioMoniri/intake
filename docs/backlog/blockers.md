# Blockers — what is waiting on a named human

> Format (LOOP.md step 7): one row per ask. `HUMAN_BLOCKERS.md` is the register
> of record — every row here cross-references its HB id. A row leaves this file
> when the HB row closes, never because a workaround was found.

| issue | status | who | the one sentence they must answer | HB id |
|---|---|---|---|---|
| INT-001 | awaiting-human (container evidence) | owner | Free 80–100 GB of disk and raise Docker RAM so `make dev` + the obs/security tiers can run — 18 GiB free and 14.1 GB Docker RAM today. | HB-I1, HB-I2 |
| INT-043 | awaiting-human (clinical sign-off) | physician of record | Review and sign the base.intake / base.red_flags drafts (PR left open under CODEOWNERS) — every ask_tr and rule is L0 agent draft until your signature. | HB-C1, HB-C2, HB-C7 |
| INT-043 | awaiting-human (turn budget) | clinician (ClinicalAuthor, 00 §5 Q8) | Resolve the fast-mode collision: the content list is 16–21 turns against a ≤ 18 budget before the six new slots — cut content, raise the budget, or compound questions? | HB-C5 |
| INT-043 | awaiting-human (six additions) | clinician | Confirm wording, placement and applicability bands of the six drafted slots (pregnancy_status, lmp_date, immunosuppression, anticoagulant_use, weight_kg, time_last_known_well) — the reproductive-age band constants are deliberately unfilled. | HB-C6 |
| INT-116+ | note | owner | Archive the official Turkish PHQ/GAD PDFs into the technical file now — phqscreeners' terms page already 404s and the PDF is the only durable evidence of the grant (00 §2). | — |
| licensing | note (non-blocking) | owner | Confirm the split "Apache-2.0 for packages/protocols, proprietary for everything else" (07 §4) — bootstrapped that way pending your word. | — |
