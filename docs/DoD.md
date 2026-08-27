# Definition of Done (per issue == per PR)

Two lists. The first you can check yourself and must. The second you cannot — and pretending otherwise is the failure this section exists to prevent.

## A. Self-assessable — check every line before opening the PR
- [ ] PR maps to exactly one issue (`INT-xxx:` title, `Closes #n`); branch `int-<n>-<slug>`; squash merge only.
- [ ] Acceptance criteria quoted verbatim in `docs/evidence/INT-xxx.md`, one check per line, each with the artefact that satisfies it.
- [ ] `docs/evidence/INT-xxx.md` contains the **red run** (the failing test output from before the implementation existed), then the **green run**, then `make check`, `make safety` and `make security` output, then the coverage delta.
- [ ] The red run is real. A test that could not have failed — `assert True`, a tautology, a mock asserting itself — is a rejected PR, not a weak one.
- [ ] `make check` / `make safety` / `make security` green **from a clean clone**, not only incrementally.
- [ ] Every invariant the change touches still passes, named individually in the evidence file. If the change touches none, say so explicitly.
- [ ] Types clean (`mypy --strict` / `tsc --noEmit`); lint clean; coverage thresholds met or raised, never lowered.
- [ ] Zero placeholders: `no_placeholders` green; no skipped/xfail tests; no mocks outside tests. The only permitted unfilled value is `TODO: <what> requires clinical sign-off` inside a `draft_needs_source` rule that the compiler refuses to serve.
- [ ] **No new PHI egress path.** Enumerate every outbound call the change adds — including telemetry, crash reporting, and anything a library does on your behalf — and show each is either local or refused by the egress allow-list. "It doesn't send PHI" is a claim; the allow-list test is the evidence.
- [ ] **Every new metric is registered in `metrics_catalog.yaml`**, or CI fails. Same for a new service and the four monitoring endpoints, its SLO file and its probe.
- [ ] **Licences verified for any new dependency or model** — from the raw LICENSE blob, not a badge — with the allow-list check green and `licence_verified_at` recorded for anything on the PHI path.
- [ ] **No accuracy claim added** to `docs/regulatory/`, `docs/legal/`, patient or clinician copy. Measurements go to `docs/evidence/` with a date and a named corpus, phrased as measurements.
- [ ] `tr` and `en` strings added; `tr` is the source of truth; Turkish clinical copy marked for clinician review if patient-facing; no `text-transform`, no mid-word truncation, no `word-break: break-all`.
- [ ] Security: no PHI in logs; inputs validated; consent scope checked on new data access paths; secrets from OpenBao only; identifiers tokenized; the feature's row in `files/10 §9` exists or is updated.
- [ ] Legal: the issue's `legal:` codes re-read in `files/06 §1`; new personal-data fields annotated `{category,purpose,basis,retention,recipients}`; consent scopes declared on new routes; legal strings only from `docs/legal/strings.yaml`; device-boundary check when the feature touches triage or instruments.
- [ ] Observability: new flows emit catalogued metrics + traces; errors carry ids not payloads; dashboard panel + alert rule added when a new SLO or critical path is introduced.
- [ ] Docs: PROGRESS.md entry; `issues.yaml` status + GitHub issue updated; every blueprint file the change touches updated **in the same PR**; ADR if architecture changed; CHANGELOG line.
- [ ] **`00_STATE.md` updated in the same commit as the decision it records.** A decision that lands without a `00` row is a decision that will be re-litigated in two weeks by someone who cannot find it. Reversals mark the old row withdrawn with the reason; they never delete it.
- [ ] Commit message says **what changed and why**, not just what.
- [ ] Demo: the acceptance can be shown via a command or a simulator scenario (`make demo-<id>`).
- [ ] Accessibility (UI tasks): labels, contrast, dynamic type to 200 %, full operation with sound off, full operation without reading — and conformance reported in the Turkish checklist's own BK numbering where it applies.

## B. Cannot be self-certified — these need a named human, and the PR stays open
Mark the issue `awaiting-human`, add the ask to `docs/backlog/blockers.md` with the `HUMAN_BLOCKERS.md` id, and continue with the next issue. **A green PR with one of these outstanding is not done. It is green.**
- [ ] **Clinical content is `awaiting-clinical-review`, never `done`.** Any rule, threshold, item wording, action script or patient-facing clinical sentence is L0 until a **named licensed physician** signs the PR under CODEOWNERS — a paediatrician specifically for paediatric rules. "Reviewed by the team" is not a signature, and neither is a passing golden test: the goldens were written by the same process that wrote the rule.
- [ ] **Legal text, consent wording, intended purpose, retention and the device boundary** need counsel or the owner, per `06`.
- [ ] **Vendor or contract evidence** (`live-smoke`) and **on-hardware evidence** (`gpu`) close their issues; recorded fixtures do not.
- [ ] **Anything with a `HUMAN_BLOCKERS.md` row.** Check the file before deciding you are blocked — and before deciding you are not.
- [ ] **Any claim about clinical performance.** You cannot certify a sensitivity, and the policy is that we do not publish one at all.

## C. The honest note
Every item in list A is a thing a machine can check about a machine's work. **Nothing in list A tells you whether the clinical content is correct**, and that is the only property this product is really judged on. The gates exist so that the human's scarce attention lands on list B and is not spent on things a script could have caught. If you find yourself wanting to move an item from B to A, you have found the failure mode.
