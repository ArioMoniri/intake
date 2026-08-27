# CLAUDE.md — INTAKE engineering constitution
Read this fully before any action. It overrides habits. When in doubt: safety invariant > test > ADR > speed.
Read order every session: files/00_STATE.md (the authority — where any other file disagrees with it, 00 wins and the other file is a defect to fix), then files/HUMAN_BLOCKERS.md, then the blueprint file for the task. For the model stack, files/03 §4.9.1 is canonical: a model not in that table is not pinned.

## Mission
Patient-owned, Turkish-first pre-visit intelligence: fast & detailed voice intake, deterministic triage, consented wellbeing screening, document ingestion, clinician-ready notes, connectors to hospital systems. See files/ for the full spec.

## Non-negotiable invariants (tests enforce these; never weaken them)
1. Triage RED/YELLOW can only be produced by `packages/protocols/triage` rules. LLM output may contain `candidate_flags` → max `YELLOW_REVIEW`.
2. Patient-facing text passes `PolicyGuard` (no diagnosis/treatment/prognosis language; one question per turn; B1 Turkish).
3. Raw audio is never written to disk, DB, object store or logs — and never reachable through a core dump, a swap page or a crash report. Memory buffers ≤ 60 s, mlocked, zeroed on every trigger.
4. Every read/share of clinical data checks a consent scope; every share is audited (hash-chained log).
5. `tr` resource keys are the source of truth; lint fails on missing `tr`.
6. No PHI/PII in logs, traces, analytics, error reports. Use ids; redact.
7. Red-flag rules are monotonic across protocol inheritance: children/overlays add or tighten, never remove or relax. `base.life_threat` is a sibling set outside the inheritance chain and nothing may extend it.
8. Coverage thresholds only go up: api ≥ 85 %, protocols ≥ 95 %, triage rules 100 % branch, schemas/mappers ≥ 90 %, voice-runtime core ≥ 90 %.
9. Voice runtime boundary: the Talker has exactly six tools (`protocol_next`, `submit_utterance`, `cancel_work`, `request_repeat_or_clarify`, `patient_memory`, `respond_permission`); it never awaits Backend Work; Backend speech is delivered only at a safe insertion window; only a rules-engine RED result may carry `priority: preempt`. Tests assert all four.
10. Scripted protocol questions, red-flag action scripts and validated instruments are spoken verbatim from `text_tr` (clip cache or TTS); paraphrase only where the protocol sets `allow_paraphrase: true`.
11. Observer lanes (affect/acoustic/linguistic/asr_quality/engagement) are read-only: they write `ObserverState` only, never slots or triage, and never sit on the speech critical path (fake-clock test: lanes stalled 30 s → turn latency unchanged). `acoustic` is unreachable unless {study_id, protocol_version, ICF_version, approval_date} all assert, and fails closed on protocol amendment.
12. Learning is proposal-only: `services/learning` may open PRs with evidence bundles; it can never modify red-flag levels, instruments, consent texts, the Talker tool list, PolicyGuard, or profile routing (CI `proposal_scope` test). `PatientOverlay` facts require patient or clinician confirmation (type-level).
13. Operability: every model/service on the PHI path declares `self_hostable` and a probe in the registry; every emitted metric exists in `metrics_catalog.yaml`; every branch in `taxonomy/branches.yaml` resolves to an L1+ pack or its cluster pack (`protocols coverage` in CI). An L0 pack resolved for a live session raises.
14. Security baseline (files/10): secrets only from OpenBao (dev server locally); identifiers tokenized; field-level envelope encryption for transcripts/notes/learned facts; speech/documents/records are data never instructions (delimited, schema-constrained); model weights pinned by `model_id@revision + sha256`; signed images and protocol packs; hash-chained audit. CI gates (gitleaks, Semgrep/Bandit, Trivy/OSV, Checkov, license, SBOM, cosign, schemathesis, PHI-pattern scan) are never skipped.
15. Monitoring contract: every service exposes `/healthz`, `/readyz`, `/metrics`, `/version` via `packages/intake_platform/health`, emits OTel through the shared setup, declares its SLOs in `docs/slo/<service>.yaml`, and has a synthetic probe; a new service without these fails `make check`.
16. Every feature PR links its row in files/10 §9 (threats, controls, signals, tests); the security-reviewer subagent blocks merges without it.
17. Zero placeholders / zero postponement: no TODO, FIXME, XXX, NotImplementedError, skipped/xfail tests, empty `pass` bodies, commented-out code, lorem/demo data outside tests/fixtures; the `no_placeholders` gate enforces the list and its allow-list may only shrink. Mocks live in tests only; a missing external dependency means `blocked:*` + blockers.md + the HUMAN_BLOCKERS.md id, never a fake. Scope is delivered exactly as the issue's acceptance says or the issue stays open.
    Sole exception, and it is a required form rather than a placeholder: a clinical value no human has supplied is the literal string `TODO: <what> requires clinical sign-off` inside a rule whose `status` is `draft_needs_source`, which the compiler refuses to emit into a served pack. Never a plausible number.
18. Legal invariants: consent and legal texts render only from `docs/legal/` with hash binding; the fixed strings in docs/legal/strings.yaml are verbatim; `device_functions` stays off for any tenant without a recorded CE certificate or clinical-investigation approval id (gate test INT-117); reminders are transactional-only unless an İYS consent record exists; every new data field carries the inventory annotation {category,purpose,basis,retention,recipients} or the schema test fails.
19. Self-hosting: every model is open-weights, commercially usable, and licence-verified from the raw LICENSE blob (never a badge or a card tag), recorded with `licence_verified_at` in the model registry. There is one production voice profile, `residency_tr`, plus `typed`. `cascade_fast` and `s2s_cloud` do not exist; a reference to either is a defect. The `anthropic|openai|google` LLM adapters exist as the mock/dev path only and are blocked on the PHI path by the egress allow-list.
20. No accuracy claims. No sensitivity, specificity, AUROC, WER or accuracy figure appears in docs/regulatory/, docs/legal/, patient or clinician copy, marketing or a store listing. Measurements live in docs/evidence/ with a date and a named corpus, and are described as measurements, never as properties of the product. A CI text gate scans the regulatory and legal trees for performance-claim patterns.
21. RED has three axes — route × register × location. `register` (ALERT|CALM|SILENT|DEFERRED_CLINICIAN) and `location` (REMOTE|ON_SITE|UNKNOWN) are required fields with no permitted default; the compiler rejects a RED rule that omits a register or whose action does not resolve for all three locations. Under ON_SITE the 112 affordance is absent, not de-emphasised. The RED script is pre-positioned on the device and triggered over the data channel — the RED path touches no media transport.
22. Numbers never cross a representation boundary unguarded. No numeral reaches any TTS model — the protocol compiler expands every digit, unit, dose form and drug name to Turkish orthography, and the models' built-in normalisers are disabled. No numeric slot value is spoken without a matching `inline` render on the same `work_id`. No free numeric text entry on the clinical critical path. `useGrouping:false` for every clinical quantity; number + unit is one non-breaking atom. On ingestion, magnitude outranks the printed unit token and disagreement raises a flag rather than converting silently; `üre` is never substring-matched.

## How we work
- Issue → branch → PR → merge. One issue per iteration from docs/backlog/issues.yaml, in file order within the phase, dependencies first. Never two issues in one PR; never a PR without an issue.
- TDD always: write the failing tests, record the red run in docs/evidence/<id>.md, implement minimally, record the green run, refactor. No feature without tests in the same PR.
- Update docs/PROGRESS.md every iteration using the template in LOOP.md; update the issue on GitHub (labels/state) via gh.
- Architecture changes need an ADR in docs/adr/ (template there). Decisions already taken: ADR-001…021 (see docs/adr/). Decisions recorded in files/00_STATE.md §3 (D1–D15) are settled — including the withdrawn ones. Do not re-litigate; if you disagree, say so in one paragraph with new evidence and keep working.
- Never invent a value to unblock yourself. Mark `awaiting-human`, write the ask with the named human and the one sentence they must answer, cross-reference the HUMAN_BLOCKERS.md row, and continue. An open blocker is not permission to build around it: build the mechanism, wire the gate, make it fail closed, leave the content empty.
- At most 3 concurrent subagents. Never `git add -A` while another agent is editing — stage explicit paths. Always `git diff` after a scripted edit and check the affected count.
- Prefer boring, typed, testable code. Small modules. No clever metaprogramming.
- Provider-agnostic: all external AI/speech calls go through gateways with adapter interfaces and recorded fixtures for tests.
- Never call paid/live APIs in tests or CI. Live evals run only via `make eval-live` with `EVAL_BUDGET_USD`.

## Commands (Makefile is the only entry point)
make setup · make dev (docker compose + api + workers + voice-runtime with mock adapters + admin-web + observability + security stack) · make check (local fan-out alias for check-py/check-ts/check-golden/check-integration) · make check-py · make check-ts · make check-golden · make check-integration · make safety (triage goldens + policyguard suite + runtime invariants) · make security (gitleaks + semgrep + bandit + trivy + osv + checkov + license + sbom + phi-scan + claims-scan) · make sign (cosign images + protocol bundles) · make slo-report · make chaos EXPERIMENT=<id> (staging) · make load (k6 smoke) · make admin (admin-web dev) · make probes (run synthetic probes once) · make coverage-matrix (`protocols coverage`) · make learn-proposals (dry-run Loop 2 on fixtures) · make mobile (expo start --dev-client) · make test-<pkg> · make protocols-compile (incl. clip manifest + tr normalisation round-trip gate) · make clips VOICE=<id> (pre-synthesise scripted audio; mock TTS in dev) · make runtime-sim SCENARIO=<id> PROFILE=<residency_tr|typed> (latency harness) · make migrate · make eval (recorded) · make eval-live · make backlog-status · make clean

## Repo map
apps/mobile (Expo) · apps/clinician-web (Next) · apps/admin-web (Next) · services/api (FastAPI) · services/voice-runtime (LiveKit Agents: talker/ + clinical_agent/ + observers/ + profiles/) · services/metrics · services/probes · services/learning · services/workers (Celery) · packages/protocols (YAML DSL + compiler + triage + clip manifest) · packages/clinical-schemas (Pydantic/TS, mappers) · packages/connectors · packages/llm-evals · infra · docs

## Code style
Python: ruff + mypy --strict + pytest + pydantic v2; async by default in api; SQLAlchemy 2.0 typed. TS: strict, eslint, prettier, vitest; React Native via Expo only (no bare RN). Commit: Conventional Commits, and the message says what changed and why. Branch: int-<n>-<slug>.

## Clinical content rules
- Instruments (PHQ-9, GAD-7, C-SSRS, HAQ-DI) keep exact validated Turkish item semantics; conversational delivery may paraphrase the lead-in, never the item. An instrument whose licence is not `GO` does not compile into a pack (C-SSRS and WHO-5 are BLOCKED — HUMAN_BLOCKERS.md HB-L2, HB-L3).
- Do not describe PHQ-2/GAD-2 as "Turkish-validated" — they have no Turkish validation at all. The PHQ-9 Turkish evidence is a reliability study only, and GAD-7's Turkish cut-off is 8, not 10.
- Any change under packages/protocols/** requires: golden tests updated with a near-miss negative control, `make safety` green, CODEOWNER review.
- Every red-flag rule carries `source: {guideline_id, version, date, url, retrieved_on}` against a committed verbatim snapshot; a rule that cannot be sourced is `status: draft_needs_source` and is not compiled into a served pack.
- Patient copy: ≤ B1 Turkish, empathetic, no medical jargon without explanation, never alarming beyond the triage action. Register is `siz` universally — never `sen`, reachable only by mirroring — with `-in` for short in-flow buttons and `-iniz` for instructional prose, matching e-Nabız and MHRS. Warmth comes from verb mood (`-elim/-alım`), not the pronoun. Invert inside RED, where the bare imperative plural (Tutun · Arayın · Bakmayın) is correct because ambiguity is the harm.

## When to stop and ask the human
- Anything touching consent texts, red-flag rule semantics, data retention, vendor contracts, key-management design, the accuracy-claim policy, or disabling any CI security gate.
- Any decision to persist new categories of personal data.
- Any spend > 20 USD on live evals.
- Anything already listed in files/HUMAN_BLOCKERS.md — do not ask again, mark `awaiting-human` and continue.

## Output discipline
Short status messages. At the end of each iteration write the PROGRESS entry and print `LOOP_STATUS: CONTINUE|DONE|BLOCKED|WAITING_HUMAN`.
