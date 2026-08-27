# GOALS
## North star
Every patient walks into the room with a clinician-ready pre-visit note, and every clinician reads it.

## Product goals (P1 exit)
G1 Fast-mode Turkish voice intake completes in ≤ 4 min median with ≥ 80 % completion.
G2 Clinician note acceptance (accept/edit vs reject) ≥ 70 %, rising to ≥ 85 %.
G3 Triage: 100 % sensitivity on RED goldens; crisis path completion 100 %. The false-RED ceiling is deleted — see the Safety note below.
G4 Round-trip voice latency (last patient speech sample → first agent audio on device) is stated **per network profile** (02 §8.1), never as one number: on mid-LTE, scripted ≤ 450 ms p50 / ≤ 680 ms p95 and dynamic ≤ 1000 ms p50 / ≤ 2100 ms p95; RED preemption ≤ 300 ms p99 via the data channel; the Talker never waits on Backend Work.
G5 Records ingestion: ≥ 90 % of lab values extracted with correct LOINC + unit on our own held-out Turkish corpus — an internal measurement with a date and a corpus name, never a published claim.
G6 Zero PHI incidents; DPIA v1 approved; consent opt-in ≥ 70 % for voice.
G7 No patient ever runs on bare `base.intake`, and every patient is evaluated against the universal `base.life_threat` set. (Softened from "100 % of booked branches served by an L1+ pack", which was true only in a sense that would not survive contact with a cardiologist: `cluster.medical` puts ~30 branches through a single HPI.)
G8 Experience: CSAT ≥ 4.3, NPS ≥ 40, time-to-first-question ≤ 3 s, note ready ≤ 60 s after wrap-up; all tracked in the admin console.

## Safety goals (replacing the deleted false-RED ceiling)
S1 Primary metric is **misses, not false positives**: zero clinician-confirmed missed time-critical conditions, measured by chart-linked follow-up of a sample of GREEN sessions — not clinician self-report, which under-detects.
S2 RED is un-bundled into tiers so a ceiling applies where it belongs: `EMERGENCY_NOW` ≤ 0.5 % (tight) · `SAME_DAY_ACIL` (several % is acceptable) · `EXPEDITE`.
S3 Per-rule false-RED rates with per-rule review through the console queue, which is the unit of governance.
S4 Per-rule extraction sensitivity and specificity against a Turkish clinical reference standard — covering agglutinative negation and evidentiality, second-language Turkish speakers, and a "did not understand" state distinct from "no". **Gates P1 exit**: a deterministic rules engine over probabilistic inputs is not deterministic.
(The old `false-RED ≤ 2 %` target is deleted. It is arithmetically incompatible with the rule set — ~30 RED rules at ~0.1 % each ≈ 3 %, and Ottawa SAH carries ~23 % specificity *by design* — and a hard ceiling creates continuous pressure to weaken rules, which is the exact failure the monotonicity guardrails exist to prevent. Symptom checkers that became less risk-averse between 2015 and 2020 ended up missing over 40 % of emergencies.)

## Engineering goals
E1 `make check` < 10 min in CI as four parallel jobs; flaky tests = 0 tolerated (quarantine + fix within 48 h).
E2 Every LLM/speech call traced with prompt/model/version; every model referenced as `model_id@revision + sha256`; reproducible sessions via protocol hash.
E3 A model or profile swap is a config change, proven by contract tests per adapter and profile-parity simulator runs across `residency_tr` and `typed`.
E4 A new specialty pack is authored by a clinician in YAML, compiled and tested without engineering help; L0 drafts for every branch regenerate from the taxonomy in one command.
E5 Every model/service on the PHI path is self-hostable and probed; the registry and the release gate are built in P0 and enforced from P2.
E6 Learning proposals ship as PRs with evidence bundles, through clinician approval and canary — never as silent changes.
E7 Security & reliability: zero PHI in telemetry (scan pass 100 %); vulnerability SLAs met (critical 72 h / high 7 d); SLO attainment reported monthly; MTTR < 4 h; restore drill each quarter; pen-test before pilot with findings closed.
E8 Every licence on the PHI path verified from the raw LICENSE blob with a `licence_verified_at` date; CI fails the release if a row lacks one.

## Delivery goals (how we ship — enforced, not aspirational)
D1 One issue at a time, in order; every merged PR maps to exactly one issue with recorded red→green evidence.
D2 Nothing merged with placeholders, skipped tests, demo stubs or silently reduced scope; `no_placeholders` and `evidence_check` stay green on every PR.
D3 Blocked ≠ done: vendor/GPU/human-gated issues close only with live-smoke / on-hardware / sign-off evidence; blockers are listed for the human in `docs/backlog/blockers.md` with their `HUMAN_BLOCKERS.md` id, never worked around.
D4 Legal and regulatory artefacts (INT-210…INT-227) ship as issues with the same rigour — the tenant gate (INT-250) refuses go-live without them.
D5 Docs move with code: blueprint files, CLAUDE.md pointers, runbooks and the metrics catalogue are updated in the same PR that changes behaviour. `00_STATE.md` is updated in the same commit as the decision it records.

## Anti-goals
Not a symptom checker that diagnoses. Not an AI scribe competing in Epic shops. Not storing voice. Not a chatbot that chats — it collects, structures, routes. **Not a product that publishes accuracy claims.**
