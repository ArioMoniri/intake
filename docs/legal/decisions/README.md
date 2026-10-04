# Legal decisions register (owner decision D25)

Owner, 3 Oct 2026, in chat: *"also set an legal profesional subagetns to approve legal parts or review them like forensics i give permisison with this message"*. Recorded as D25 in `files/00_STATE.md` §3 (INT-471, GitHub #800).

- **Who decides.** A sourced legal-author agent decides each open legal item; a separate legal-reviewer agent, spawned by the orchestrator, verifies it and its verdict is recorded. Open legal questions are routed to this lane first. Items on CLAUDE.md's stop-and-ask list (consent texts, data retention, vendor contracts, new categories of personal data, the performance-claims policy of invariant 20, disabling a CI security gate) and HUMAN_BLOCKERS rows that name the owner still go to the human; the lane's output there is a recommendation.
- **Scope.** Synthetic and test use only. A licensed Turkish lawyer countersigns before any real patient: `real_patient` scope needs every field of the countersign block (lawyer, baro, sicil number, the full 40-hex signed commit, a date no earlier than the reviewer's verdict, and an evidence file under `docs/evidence/` that exists), and `intake_platform.legal.decisions.clearance` refuses every decision for a real patient until then. This mirrors D17/D18 and the physician sign-off of HB-C1.
- **No answer without a source.** Every source is an official text (mevzuat.gov.tr, resmigazete.gov.tr, kvkk.gov.tr, saglik.gov.tr, aile.gov.tr; for a standard, its publisher) quoted, four words or more, against a verbatim snapshot under `packages/intake_platform/legal_decisions/sources/` whose header carries the same url, Resmî Gazete date and number (or standard version) and retrieval date. Every answered value names the source or repository sentence that supports it. A question no retrieved text answers stays `draft` with a `legal_gap` sentence that names what is missing and which source would settle it; its value is absent, never defaulted.
- **Status.** `draft` (no answer) → `proposed` (sourced, awaiting the reviewer) → `active` (the reviewer's `agree`, or `agree_with_changes` once the changes are applied and recorded in `verifier.notes`; the reviewer's role is not the author's). Only `active` may be used, and only in synthetic and test sessions.
- **What this register does not do.** It fills no counsel field anywhere: `docs/legal/data-categories.yaml`, `docs/legal/documents.yaml` and the hash-bound legal texts are unchanged, and HUMAN_BLOCKERS legal rows stay open for the licensed lawyer.

Machine-readable entries: `packages/intake_platform/legal_decisions/LD-NN.yaml`, read through `intake_platform.legal.decisions` (tests: `tests/legal/test_legal_decisions.py`).

| Decision | Title | Status | Reviewer verdict | Lawyer countersign |
|---|---|---|---|---|
| [LD-01](LD-01.md) | Adli Tıp: the report-purpose item, and whether the Sağlık Raporları Yönetmeliği governs forensic reports | `active` | agree_with_changes | none |
| [LD-02](LD-02.md) | Minors and proxy answers (HB-L20) in synthetic and test sessions | `active` | agree_with_changes | none |
| [LD-03](LD-03.md) | KVKK inventory rows: family history, relatives' health and consanguinity; the hearing-voices item (Q16) | `active` | agree | none |
| [LD-04](LD-04.md) | Occupational items: work-related sick leave, job tenure and household tuberculosis contact — category and basis | `active` | agree_with_changes | none |
| [LD-05](LD-05.md) | WCAG 2.2 SC 2.2.1: classification of the RED no-answer wait | `active` | agree_with_changes | none |
| [LD-06](LD-06.md) | Admin metrics and telemetry for research and improvement: purpose, anonymisation, cell size, retention | `active` | agree_with_changes | none |
