# Blockers — what is waiting on a named human

> Format (LOOP.md step 7): one row per ask. `HUMAN_BLOCKERS.md` is the register
> of record — every row here cross-references its HB id. A row leaves this file
> when the HB row closes, never because a workaround was found.

| issue | status | who | the one sentence they must answer | HB id |
|---|---|---|---|---|
| INT-001 | awaiting-human (container evidence) | owner | Free 80–100 GB of disk and raise Docker RAM so `make dev` + the obs/security tiers can run — 18 GiB free and 14.1 GB Docker RAM today. | HB-I1, HB-I2 |
| INT-038 | awaiting-human (consent texts; mechanism shipped, fails closed) | owner + counsel (via INT-210) | Author the eleven Turkish açık rıza texts (core, voice, wellbeing, lane:affect, lane:linguistic, documents, learning:personal, learning:service_improvement, satisfaction, share, research) into `docs/legal/consents/` in the loader contract (`---` / `consent_text_version: <v>` / `---` / copy; filename = purpose with `:`→`.` + `.tr.md`) — until then every NEW grant refuses fail-closed (ConsentTextMissingError) and the dev tier runs on unbound seed grants only. | — (legal-text authoring is INT-210's deliverable; no HB row exists for it) |
| licensing | note (non-blocking) | owner | Confirm the split "Apache-2.0 for packages/protocols, proprietary for everything else" (07 §4) — bootstrapped that way pending your word. | — |
