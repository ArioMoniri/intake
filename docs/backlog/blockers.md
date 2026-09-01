# Blockers — what is waiting on a named human

> Format (LOOP.md step 7): one row per ask. `HUMAN_BLOCKERS.md` is the register
> of record — every row here cross-references its HB id. A row leaves this file
> when the HB row closes, never because a workaround was found.

| issue | status | who | the one sentence they must answer | HB id |
|---|---|---|---|---|
| INT-001 | awaiting-human (container evidence) | owner | Free 80–100 GB of disk and raise Docker RAM so `make dev` + the obs/security tiers can run — 18 GiB free and 14.1 GB Docker RAM today. | HB-I1, HB-I2 |
| INT-038 | awaiting-human (consent texts; mechanism shipped, fails closed) | owner + counsel (via INT-210) | Author the eleven Turkish açık rıza texts (core, voice, wellbeing, lane:affect, lane:linguistic, documents, learning:personal, learning:service_improvement, satisfaction, share, research) into `docs/legal/consents/` in the loader contract (`---` / `consent_text_version: <v>` / `---` / copy; filename = purpose with `:`→`.` + `.tr.md`) — until then every NEW grant refuses fail-closed (ConsentTextMissingError) and the dev tier runs on unbound seed grants only. | — (legal-text authoring is INT-210's deliverable; no HB row exists for it) |
| INT-016 | awaiting-human (anchor destination; verifier shipped, fails closed) | owner | Which organisation's object store, or which named Turkish TSP, receives the hourly audit-chain head — and who signs that arrangement? Until one is named the verifier has nothing independent to check against, so it sets `sec_audit_chain_ok` 0 and exits 3 rather than reporting a chain that merely agrees with itself. | HB-I8 |
| INT-016 | awaiting-human (production WORM target) | owner | Accept MinIO with a documented CVE-watch and a paid-support escape hatch, or move audit WORM to a purpose-built target — Garage implements no S3 Object Lock and would void the 10-year guarantee silently? Dev/CI WORM is proven server-side; production has no configured target. | HB-I9 |
| licensing | note (non-blocking) | owner | Confirm the split "Apache-2.0 for packages/protocols, proprietary for everything else" (07 §4) — bootstrapped that way pending your word. | — |
