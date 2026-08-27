# TDD & test strategy

## The question this suite answers
For most software the test asks *"does it work?"* Here the test that matters most asks **"does it still refuse?"** — refuse to lower a triage level, refuse to speak a diagnosis, refuse to write audio, refuse to serve an unsigned pack, refuse to reach the acoustic lane without a study id, refuse to say a number the screen does not also show. Every one of those is a refusal, and a refusal is invisible when it stops working. Nothing goes red. A patient just gets an answer they should not have got.

That is why the ordering below is not the conventional one.

## Rules
1. **A failing test first, always.** The evidence file quotes the red run. A PR whose tests could not have failed — `assert True`, a tautology, a mock asserting itself — is rejected by test-writer review, not merely queried.
2. **Every safety rule ships with a golden test AND a near-miss negative control.** Not a random negative — a **near miss**: the case one clause away from firing. Chest pain that is reproducible on palpation against chest pain that is not. A headache reaching maximum in six minutes against one reaching it in fifty seconds. A 39.0 °C infant of fourteen weeks against one of eleven weeks.
   **The negative matters more than the positive, and this is the part that gets it backwards.** A positive golden passes *by construction*: you wrote the rule from the case, so the case fires. It detects only under-triggering — the rule you broke while refactoring. **Over-triggering is invisible in production.** Nobody files a bug saying "I was told to go to the emergency department and I did not need to"; they go, they wait, they are sent home, and the signal reaches us months later as alert fatigue, as clinicians who have stopped reading the RED banner, and as a false-RED rate nobody can attribute to a rule. By then the rule that did it is one of thirty and the evidence is gone. The near-miss negative is the only artefact that catches it **at the moment it is written**, which is the only moment it is cheap.
3. **A deliberately broken RED rule must fail the suite.** Mutate one — invert a comparison, widen a bound, drop a clause — watch `make safety` go red, revert it, and put both runs in the evidence file. **This is a P0 exit artefact, not a nicety**: it is the only proof that the golden suite is load-bearing rather than decorative, and a suite that stays green through a broken RED rule is worse than no suite because it is trusted.
4. **Property tests for anything with a monotonicity or invariance claim.** Not examples — properties, over generated inputs:
   - **Monotonicity**: adding a rule, an overlay or an inherited pack never lowers a triage level (`overlay_monotonicity`).
   - **Invariance**: the must-ask set is *identical* with the observer lanes enabled and disabled — order may change, membership may not (`must_ask_invariance`). This is what makes "lanes are read-only" true rather than true-on-a-technicality.
   - **Round-trip**: FHIR ↔ internal mappers under hypothesis.
   - **Determinism**: `replay(event_log)` reproduces engine state, note deltas and step order byte-for-byte, including under fuzzed, truncated and reordered logs.
   - **Concurrency**: FIFO + single-in-flight + serialised writes under concurrent submission; no lost or reordered slot updates.
5. **Real integrations are tested three ways** — unit (pure), contract (recorded fixtures, in CI), live smoke (`make live-smoke`, only with keys, output stored as evidence). An adapter issue labelled `live-smoke` is not done on fixtures alone.
6. **Tests are deterministic**: freeze time, seed randomness, record network. Fake clocks for every latency assertion — a wall-clock latency test is a flake generator.
7. **No skipped, xfail, quarantined-forever or commented tests.** A flaky test is fixed or deleted-with-ADR within 48 h.
8. **Mutation testing (mutmut) on the triage evaluator before P1 exit.** The goldens claim to constrain the evaluator; mutation testing is how you find out whether they do.
9. **Coverage thresholds only go up.** api ≥ 85 %, protocols ≥ 95 %, triage rules 100 % branch, schemas/mappers ≥ 90 %, voice-runtime core ≥ 90 %.

## Pyramid
1. **Unit** (pytest/vitest): pure logic — slot schemas, mappers, rule evaluator, compiler, reducers, components.
2. **Contract**: adapter interfaces (STT/TTS/LLM/connectors) against recorded fixtures; OpenAPI schema tests (schemathesis) for the API.
3. **Golden**: protocol resolution → expected Questionnaire/slot-schema snapshots; **triage cases ≥ 200 with ≥ 60 RED, each RED paired with its near-miss negative**; note renderers → text-diffed snapshots.
4. **Property**: the claims in Rule 4, under hypothesis.
5. **Simulation**: LLM patient simulator (recorded in CI, live nightly) → rubric: must-ask coverage, safety, tone, one question per turn.
6. **Runtime simulation** (fake clocks, mock adapters): the voice-runtime invariants of `files/03 §4.6` — non-blocking Talker, six-tool surface, RED-only preemption ≤ 300 ms **asserted to touch no media transport**, FIFO + single in-flight + serialised writes, idempotent insertion-window delivery, verbatim scripted text, and **profile parity across `residency_tr` and `typed`** (there are two profiles, not four).
7. **Integration**: docker compose up (api + db + redis + hapi + minio) → session lifecycle with mock adapters.
8. **E2E** (P1+): Maestro flows on iOS simulator for onboarding → typed intake → review → share.
9. **Console & learning**: contract tests for `/admin/*` with role matrices; `metrics_catalog` completeness; probe registry; `proposal_scope`, `k_anonymity`, `canary_rollback`, `overlay_monotonicity`, `learned_fact_provenance`, `taxonomy_coverage` (`09 §6`).

## Safety suite (`make safety`)
- `triage_goldens`: all RED goldens → RED; all GREEN goldens → not RED; YELLOW within tolerance; **every RED rule has its near-miss negative and the suite fails if one is missing**.
- `red_rule_mutation_probe`: the broken-rule proof of Rule 3, run as a recorded artefact at P0 exit and as a CI mutation sample thereafter.
- `red_axes_completeness`: every RED rule declares a `register`, and its action resolves for `REMOTE`, `ON_SITE` and `UNKNOWN`; `on_site_action_never_offers_112`.
- `policyguard_suite`: a corpus of forbidden patient-facing phrasings (tr/en) is blocked; allowed phrasings pass.
- `audio_no_write_guard` + `audio_no_core_guard` + `audio_no_swap_guard` + `audio_zeroization_guard` + `audio_no_telemetry_guard`: the static scan and fake-fs test prove there is no write path; the **real-crash** test forks a child, sets `RLIMIT_CORE=(0,0)`, aborts, and asserts no core file — because a fake filesystem cannot see a core dump.
- `consent_guard`: every clinical read endpoint has a consent check (AST/route-table scan + tests).
- `runtime_invariants`: RT-01…RT-08 on the latency harness; any regression in preemption latency, tool surface or delivery idempotency fails the build.
- `adversarial_suite`: RT-09…RT-14 — injection by speech and by hidden PDF text, triage manipulation, proxy impersonation, spoken TC Kimlik, adapter failover — passing in `typed` and in `residency_tr` with mocks.
- `instrument_licence_gate`: no pack compiles or serves while referencing a non-`GO` instrument; **a fixture pack referencing C-SSRS must fail the build.**
- `numeric_dual_channel_guard` + `clip_manifest_fidelity_guard`: no numeric slot value is spoken without a matching `inline` render on the same `work_id`; and the clip cache is verified by **synthesise → independent ASR → normalised diff against `text_tr`**, blocking the build on mismatch. Independent matters — diffing against the model that generated the audio tests nothing.

## Security & monitoring suite (`make security`, on every PR)
gitleaks · Semgrep (+ Bandit) · ESLint security · Trivy fs/image/IaC + OSV-Scanner (fail on critical/high) · Checkov · license allow-list **with `licence_verified_at` required for every PHI-path model** · Syft SBOM attached · cosign signing + provenance on release builds · schemathesis fuzz · MobSF on mobile builds (P1) · PHI-pattern scan on fixtures and logs · **claims-scan** (performance-claim patterns in `docs/regulatory/` and `docs/legal/`) · `metrics_catalog` completeness · `health_contract` · `audit_chain` verifier (**including flip-and-repair**, not only a single flipped row) · `tokenization_roundtrip` + `envelope_encryption` · `egress_allowlist` (a call to an unlisted host is refused and logged) · `deid_recall_by_entity_class` on a held-out human-labelled corpus, reported as a confusion matrix per class — **not** a single "< 0.1 % leak rate" on a corpus we authored, which is unfalsifiable as defined.

## Fixtures
`tests/fixtures/audio/tr/*.wav` (synthetic/consented), `tests/fixtures/transcripts/*.json`, `tests/fixtures/docs/*.pdf` (synthetic Turkish lab reports — **including the real hazards**: a wrong printed unit string, decimal separators mixed within one document, `Üre` and `Üre Nitrojeni` in the same table, a thousands separator on a five-digit result), `tests/fixtures/fhir/*.json`.
