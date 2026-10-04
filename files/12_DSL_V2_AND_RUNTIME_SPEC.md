# 12 · Protocol DSL v2 and runtime specification (25 Aug 2026)

> **Why this file exists.** The v1.4 bundle specified the *intent* of the protocol registry and the two-layer voice runtime but left the schema, the merge semantics and several safety invariants underspecified — and external verification found that four of them were not merely underspecified but **unenforceable as written**. This file is the binding specification for those parts. Where it contradicts `03_ARCHITECTURE.md`, this file wins; `03` is being updated to point here.
>
> The four that were unenforceable, and are now fixed here:
> 1. **`preempt` was authorised by a shape check** — a well-formed `{"triage_update":{"level":"RED",…}}` emitted by the extraction LLM passed the validator. Safety invariant 1 ("no LLM path to RED") was not delivered. → §5 HMAC provenance.
> 2. **Monotonicity was undecidable as posed** — base `temp_c >= 38` → child `temp_c >= 38 && age > 65` passes both stated checks while silently removing the flag for everyone under 65. → §4 three layers.
> 3. **A YELLOW could be silently dropped** — bounded retries plus an unbounded insertion window means the payload is discarded, and RT-07 only ever asserted that YELLOW does *not* preempt, never that it is *ever spoken*. → §6 bounded window + transactional note write.
> 4. **The declared `cancelled` Work state was unreachable** — nothing in the system could produce it, so on RED the patient was told to call 112 while `parse_document` kept running. → §7 `cancel_work` + queue sealing.

---

## 1. Evaluation topology

Two rule sets, evaluated independently, joined by a lattice `max`:

```
                    ┌─ base.life_threat  (constant across all sessions) ─┐
resolved_protocol ──┤                                                    ├─► TriageVerdict
   (chain + ops) ───┴─ pack red_flags (branch/overlay dependent) ────────┘
```

`base.life_threat` is **not merged** into the resolved protocol. It is a sibling set. This is what makes composition monotone *by construction*: `max` over a total order is monotone in each argument, `life_threat` is a function of `(context, set)` alone, and **no pack operation has a JSON pointer that can reach it** (§3.3 deny-list). It therefore fires for every session regardless of branch — including `cluster.excluded` (Acil), and including a session whose protocol resolution *failed*.

This is the structural answer to the finding that cauda equina, testicular torsion, limb ischaemia, acute angle-closure, neutropenic fever and GCA all lived in cluster packs and so only fired if the patient happened to book into that branch.

```
packages/protocols/
  base/life_threat.yaml        # kind: life_threat_set. No `extends:`. Nothing may extend it.
  base/intake.yaml             # the chain root
  base/ek4_mapping.yaml        # EK4Level -> Disposition, with its own source: block
  sources/<guideline_id>.txt   # committed verbatim snapshot of every cited passage
  cluster/ specialty/ visit_type/ overlay/ hospital/
  openehr/previsit_intake.v1.opt   # hand-authored, committed, sha-pinned
```

### 1.1 Three-valued evaluation — load-bearing

`not_asked` must not read as `false`. The expression context yields `Unknown` for any slot whose answer state is `not_asked` or `unclear`, and rules fire **only** on `True` (Kleene logic: `F ∧ U = F`, `T ∨ U = T`, everything else involving `U` is `U`).

A rule evaluating to `Unknown` whose referenced slots intersect `must_cover` emits a **`CoverageGap`** record — not a triage level — which is materialised into the note. A flat `negatives` list rendered exactly this case as *"elicited and absent"*; it now renders as *"never asked"*.

---

## 2. Core types

### 2.1 EK-4 acuity, separate from patient-facing disposition

Türkiye's ED regulation (Tebliğ RG 13/9/2022 s. 31952, **EK-4**) defines three colours and three physical zones but **five acuity levels**. Only `KIRMIZI_K2` carries a regulatory time target.

```python
@functools.total_ordering
class EK4Level(StrEnum):
    YESIL = "YESIL"; SARI_K2 = "SARI_K2"; SARI_K1 = "SARI_K1"
    KIRMIZI_K2 = "KIRMIZI_K2"; KIRMIZI_K1 = "KIRMIZI_K1"

    @property
    def time_target(self) -> datetime.timedelta | None:
        # ONLY KIRMIZI_K2. K1 is *immediate*, which is a different thing from a numeric
        # target — inventing "0 minutes" would create a fake SLO the metrics layer alerts on.
        return datetime.timedelta(minutes=10) if self is EK4Level.KIRMIZI_K2 else None

class Disposition(StrEnum):
    CALL_112 = "CALL_112"; GO_TO_ED_NOW = "GO_TO_ED_NOW"
    SAME_DAY_CLINICIAN = "SAME_DAY_CLINICIAN"; KEEP_APPOINTMENT = "KEEP_APPOINTMENT"
    ROUTINE = "ROUTINE"
    STATIC_SAFETY_LINE = "STATIC_SAFETY_LINE"   # device_functions=off; fixed string from docs/legal/strings.yaml
```

Acuity and disposition are separate enums **so that a `device_functions=off` tenant can suppress interpretation without touching acuity.** EK-4 acuity is computed and stored identically in both modes; only `Disposition` differs. That turns *"levels and monotonicity are unchanged in both modes"* from a prose promise into a type-level fact.

A tenant may override the `ek4 → disposition` map **only** monotonically, never toward a less urgent disposition. Compile-checked.

The 10-minute target carries its own `source:` block with `verification_status: PENDING_REGULATORY_REVIEW`; compilation refuses to publish an L3 pack while that status stands.

### 2.2 Answer states, reporter, and observation kind

```python
class AnswerState(StrEnum):
    ASKED_PRESENT="asked_present"; ASKED_ABSENT="asked_absent"
    NOT_ASKED="not_asked"; UNCLEAR="unclear"; DECLINED="declined"

class NotAskedReason(StrEnum):
    SKIPPED_BY_RULE="skipped_by_rule"      # requires skipped_by_rule_id
    TURN_BUDGET_EXHAUSTED="turn_budget_exhausted"; SESSION_ABANDONED="session_abandoned"
    SECTION_DECLINED="section_declined"; RED_PREEMPTION="red_preemption"
    NOT_YET_REACHED="not_yet_reached"

class Reporter(StrEnum):   SELF="self"; GUARDIAN="guardian"; COMPANION="companion"; KIOSK_STAFF="kiosk_staff"
class ObservationKind(StrEnum):
    SYMPTOM="symptom"          # first-person experience — only Reporter.SELF may assert it
    SIGN="sign"                # third-party observation
    RECORD_DERIVED="record_derived"
```

`reporter` is a **per-field** attribute, not a session-level flag: *a companion observes, the patient experiences.* A model validator rejects `reporter != SELF ∧ observation_kind == SYMPTOM` outright.

**What a proxy is asked is a slot attribute too** (INT-483, `docs/adr/ADR-040-subject-aware-addressing-for-proxy-sessions.md`; owner decision D24 answer 1Y). Each slot declares:

- `addressee: patient | speaker`, where `patient` is the default;
- a `proxy` block that either rewords the slot in its own verbatim `ask_tr` / `follow_up_tr` / `confirm_tr`, or sets `skip: true`.

The compiler refuses a proxy-path document while any patient-addressed askable slot of the chain has no `proxy` block. A red-flag probe is never skipped and never addressed to the speaker. A skipped step is recorded `NOT_ASKED_PROXY`, never `ASKED_ABSENT`. The op set of §3.1 is unchanged.

**Instrument scoring is gated by an unforgeable attestation token.** `score_instrument()` requires a `SelfReportAttestation`, constructible only by `attest_self_report()`, which raises if any item's reporter is not `SELF`. When attestation fails the engine emits `InstrumentNotScored` — never a number — and the FHIR projection carries `dataAbsentReason` with no `valueInteger`. This closes the case where a daughter answering PHQ-2 for her father produced `phq2: 0`, which a clinician reads as *screened, negative*.

### 2.3 `CLINICIAN_ONLY` — a third channel, enforced by the type system

Safeguarding requires a flag invisible to the patient **and to the proxy**. Displaying *"these findings may indicate non-accidental injury"* to the accompanying adult can place a child at greater risk — and the product is voice-first and speaks aloud.

Three **structurally disjoint** outcome types with no shared base class and no overlapping field names: `PatientAction` (carries `PatientSafeText`), `ClinicNotification`, `ClinicianOnlyDirective` (carries `ClinicianOnlyText`, `__str__` returns `<redacted>`, and a scoped serializer raises `ClinicianOnlyLeakError` outside `{CLINICIAN_NOTE, CLINIC_NOTIFY, AUDIT}`).

Four independent barriers: **static** (`synthesize(text: PatientSafeText)` — passing clinician text is a `mypy --strict` error); **type-graph closure** (a test walks the transitive annotation closure of `PatientSummary`, `ReviewAndSendCardSet`, `SpeechPayload`, `TalkerToolResult` and asserts none reaches a forbidden type — this is the test that fails the moment someone adds `clinician_notes` to `PatientSummary` "just for debugging"); **runtime** (the scoped serializer); and **mutation** (force-inject via `model_construct` and assert the raise).

`YELLOW_REVIEW` — the ceiling for LLM `candidate_flags` — becomes a `ClinicianOnlyDirective` and is **not an `EK4Level` at all**, which resolves the old enum overload: an LLM candidate cannot be a value of the type that drives patient-facing routing.

### 2.4 `tense:` — because a rule fires on past events

Real anaphylaxis is a five-minute event; nobody completes a pre-visit intake through one, so in practice that rule fires on *past* reactions. Every rule declares one `tense` (`now | today | within_7d | within_30d | ever`) plus a `tense_anchor` naming the slot carrying the event timestamp. The compiler rewrites `when` to include `temporal.within(anchor, tense, now)`, which returns `Unknown` when the anchor is `not_asked` — so a tense-qualified rule **cannot fire on an undated symptom**, forcing the anchor to be asked.

A `tenses:` family expands into sibling rules with distinct ids and per-tense `action_tr`. Two validators: acuity must be **non-increasing** as the tense recedes, and reusing one `action_tr` across tenses is a lint failure — *"hemen 112'yi arayın"* for an event three weeks ago is a false alarm clinicians learn to ignore.

### 2.5 `source:` per rule

Every rule at KIRMIZI or SARI level carries `{guideline_id, guideline_title, version_or_date, url, retrieved_on, quote}`, and **`quote` must appear verbatim in a committed snapshot** at `packages/protocols/sources/<guideline_id>.txt`. CI is offline and deterministic; a separate nightly job HEADs each URL and files an issue on non-200 or on `Last-Modified` newer than `retrieved_on`. Citations older than 730 days fail.

This exists because a grep of the v1.4 bundle for NICE / IDSA / USPSTF / Ottawa / BSR / ESVS identifiers returned **zero hits** — the red-flag rules carried no provenance at all, while MDCG 2020-1 clinical evaluation must rest on cited, current sources.

---

## 3. Overlay merge language

The dotted-key form (`sections.red_flags.add:`) is deleted. It was not a definable language: the v1.4 example contradicted itself about where `red_flags` lived, there was no `remove`/`replace`/`reorder` despite hospital "copy changes" requiring replace, overlay order was undefined so the same patient could produce different protocol hashes, and there was no conflict rule.

### 3.1 Typed ops

`ops:` is an ordered list of tagged objects with RFC 6901 JSON-pointer targets: `add_slot`, `add_rule`, `tighten_rule`, `override_text`, `set_attr`, `reorder`, `set_voice`, `suppress_slot`. A capability matrix restricts which layer may use which op — `HOSPITAL` gets `override_text` (the "copy changes" case that had no syntax) and `add_slot` restricted to `required: false`.

### 3.2 Deny-list — what protects the safety semantics

```python
DENY_PREFIXES = ("/life_threat", "/instruments", "/ek4_mapping")
DENY_SUFFIXES = ("/ek4", "/level", "/disposition", "/when", "/must_ask")
```

No pack op can reach the life-threat set, edit instrument item text, lower an existing rule's acuity, or rewrite an inherited predicate. `suppress_slot` on a `must_ask` slot is a hard compile error regardless of ADR.

`set_attr` moves attributes only in the tightening direction, from a **closed table**: `required false→true`, `must_ask false→true`, `allow_paraphrase true→false`, `confirm_required false→true`, `min_confidence` increase only, `notify_clinic false→true`.

### 3.3 Total order and determinism

Ops are ordered by `(layer_rank, priority, pack_id)` then declared index. `pack_id` is a total tiebreaker because ids are unique by construction. **Nothing depends on YAML list order in the parent, and nothing depends on the order patient records arrived** — `canonicalize(ctx)` sorts records by `(resource_type, canonical_id, effective_date, content_sha256)`, collapses duplicates, and converts list-valued facts to frozensets.

The context hash is asserted **separately** from the protocol hash, because it localises failures far better:

```python
def test_patient_context_hash_invariant_under_ingestion_order():
    hashes = {context_hash(canonicalize(build_context(perm)))
              for perm in take(200, itertools.permutations(records))}
    assert len(hashes) == 1
```

### 3.4 Conflicts are compile errors, never last-writer-wins

Two overlays writing the same pointer with the same value hash: idempotent, fine. With different values: **compile error naming every `(pack_id, file:line, pointer, value_hash)`**. The escape hatch is an explicit, reviewed `supersedes: [overlay.pregnant]` declaration. Because conflicting orders are *rejected* rather than resolved, merged content is order-independent **by construction, not by convention**.

Resolution fixtures must include a patient matching **three** overlays (oncology + anticoagulated + ckd) — that is where order sensitivity actually lives.

---

## 4. Monotonicity — three layers

The v1.4 check is undecidable as posed (deciding whether one CEL expression implies another). Three layers, each individually sufficient to stop the `age > 65` failure:

**Layer 1 — inherited rules are immutable.** There is no op that mutates an inherited rule; `/when`, `/ek4`, `/level`, `/disposition`, `/must_ask` are deny-suffixed and `add_rule` refuses an existing key. A test asserts inherited rule objects are **byte-identical** in the resolved document.

**Layer 2 — `tighten_rule` requires a syntactic disjunction and mints a NEW id.** The old failure mode was *replacement*. `tighten_rule` never replaces: it creates `rf.X.<qualifier>` and leaves `rf.X` live. **Even if the AST check were entirely wrong, the parent rule still fires — coverage cannot decrease.** The AST check adds the superset guarantee: the child's root operator must be `||` and one disjunct must be structurally identical to the parent. Normalisation is structural only, never algebraic — a false negative is a review comment; a false positive is a dead red flag.

`temp_c >= 38` → `temp_c >= 38 && age > 65` is now rejected at parse: root operator is `&&`.

**Layer 3 — semantic canary over a boundary-derived corpus.** AST equality is blind to context-shape changes (a slot renamed, a valueset narrowed, a `tense_anchor` added that makes a rule unfireable). `boundary_domain()` derives, for each referenced slot, every numeric literal appearing in any rule against it plus `l±ε`, every enum member, `True`/`False`, and `Unknown`. Bounded, derived from the rules themselves, and **exhaustive at every comparison boundary the authors actually wrote — which is where the bugs are.** Runs in the golden CI job.

**Runtime backstop:** `evaluate()` records `ek4_from_life_threat` and `ek4_from_pack` separately, and invariant 27 asserts `verdict.ek4 >= verdict.ek4_from_life_threat` for every session in the golden corpus.

---

## 5. Provenance-authorised preemption

`TriageVerdict` carries an HMAC-SHA256 over `(session_id, ek4, disposition, sorted rule_ids, inputs_hash, protocol_hash, life_threat_version, engine_version, issued_at, nonce, key_id)`. Verification checks far more than MAC validity: `session_id` matches the live session, `inputs_hash` equals the hash of the context just evaluated, `protocol_hash` equals the session's pinned hash, `issued_at` is within 5 s, and `nonce` is unseen. That kills replay, cross-session copy and stale-verdict resurrection, not only forgery.

The signing key is fetched from OpenBao **by the rules-engine subsystem alone**, and an import-boundary test asserts no module under `extraction/`, `observers/` or `talker/` transitively imports the attestor.

LLM output is `CandidateFlags` — **no shared base class, no overlapping field names, and no `level`, `ek4`, `disposition`, `rule_ids`, `priority` or `attestation` fields at all.** The JSON schema handed to the extraction model literally has no `level` property, so constrained decoding cannot emit one. `ExtractionResult` uses `extra="forbid"`, so a `triage_update` key is a `ValidationError` before anything else runs.

A seven-way mutation test (bare / well-formed / replayed / rule-swap / reordered / stale / nonce-reuse) asserts all are rejected, `safety.forged_triage_total` increments, and the session level does not move.

---

## 6. Bounded delivery — no YELLOW may vanish

Deadlines per delivery class, with an escalation ladder evaluated on a 100 ms tick:

| stage | window predicate | speech |
|---|---|---|
| `NATURAL` (t < soft) | silence ≥ 300 ms ∧ talker idle ∧ no pending response | as authored |
| `RELAXED` (soft ≤ t < hard) | silence ≥ 150 ms ∧ talker idle — **drops** "no pending response" | as authored |
| `INTERJECT` (hard ≤ t < terminal) | next sentence boundary; cancels remaining non-RED playback | prefixed with a cached polite-interject clip |
| `EXPIRED` (t ≥ terminal) | — | none; inline only + **mandatory** note flag |

`TRIAGE_YELLOW` uses 20 / 45 / 90 s. Under ask-ahead, *"no pending response"* is rarely true, and an anxious, elderly or low-literacy patient — exactly the personas the eval suite enumerates — may never yield the natural conjunction.

**The hard invariant is transactional, not aspirational:** for `{RED, TRIAGE_YELLOW, CLINICAL_INFO}`, the undelivered-note flag is written **inside the same database transaction** that marks the item expired, and the note write comes first. If it fails, the transaction rolls back and the item stays `PENDING` — retried, never lost. `delivery.expired_total == delivery.undelivered_noted_total` is a Prometheus recording-rule alert; divergence means the discipline broke in production.

---

## 7. Voice-runtime fixes

**§7.1 `cancel_work` replaces `get_work_status`.** Progress already arrives via `work_update` on the data channel, so no status-poll tool is needed — and the declared `cancelled` state becomes reachable. Cancellation semantics differ by lane: queued items dequeue synchronously; running background work honours a cooperative token; **running state-lane work is never aborted mid-write** — if it has committed, the write stands (you cannot un-know a red flag) and the effect is `COMPLETED_SUPPRESSED`, so a patient retraction becomes a *supersession*, not a deletion.

**On RED the queue is sealed** to `{note_finalize, clinic_notify, audit_flush}` after cancelling all background work and all queued state work. The running state item is allowed to finish — it may be the item that produced the RED.

**§7.2 `EngineSnapshot`.** `protocol_next` was a Layer-B read that could neither take the Layer-B lock (blocking the Talker, violating invariant 1) nor read outside it (torn state). The engine publishes an immutable `EngineSnapshot{version, next_step, awaiting, invalidated}` after every commit; `protocol_next` is a **lock-free atomic attribute read**; `submit_utterance` carries `engine_version` back. A stale version is *not* automatically an error — ask-ahead legitimately holds several steps `awaiting` — but a step in `invalidated` may not bind, and its transcript is preserved as **unbound narrative** rather than discarded.

**§7.3 Slot supersession, and triage leaves the queue.** `SlotCell` holds append-only revisions with `superseded_by`. The conflict policy is a table, not a heuristic; the key row is that when a safety-relevant slot is contradicted, **triage evaluates on the *union* of head and superseded values and takes `max` acuity.** So *"Göğsünüzde ağrı var mı?" → "Yok"* followed by *"göğsümde baskı var"* raises acuity, and a later *"yok yahu"* does **not** silently lower it. Session triage may decrease only via an explicit `TriageRetraction` bound to an **answered confirm step**.

`safety_relevant(slot)` is computed **at compile time** by walking every rule AST — a static property of the protocol, not a runtime guess.

**`WorkType.EVALUATE_TRIAGE` is deleted from the registry** and triage runs synchronously inside `apply_extraction`, in the same lock hold (~0.3 ms measured). This removes the head-of-line case where a RED sat behind a `parse_document`, and removes the restart hole — there is nothing to re-enqueue because triage is re-derived from slot state.

**§7.4 Two lanes.** A `state` lane (`extract_slots`, `plan_follow_ups`, `confirm_proposed_fact`, `reconcile_meds`, `note_finalize`) holds the engine lock and is strictly FIFO. A `background` lane (`parse_document`, `retrieve_records`, `draft_note_delta`, `score_wellbeing_segment`) is concurrent and **structurally cannot write slots**: it receives `ReadOnlyContext`, which has no mutator, and its effect type `BackgroundEffect` cannot express a slot write. Facts land as `ProposedFact`, which becomes a slot only via a state-lane confirm — which is also clinically correct, since imported records must pre-fill as unconfirmed.

Queue arithmetic after the split: ρ ≈ 0.25–0.35, so M/M/1 mean wait ≈ 0.3–0.5× service time. `parse_document` no longer participates.

**§7.5 Content-addressed work identity.** `work_key = sha256(session_id, work_type, step_id, input_hash, protocol_hash)`; `work_id` is derived, not minted. A restart re-submitting the same transcript produces the **same** `work_id`, so the existing dedupe starts working instead of guaranteeing duplicates on every restart. Delivery phase is written **ahead** of the first audio byte. Triage speech is at-least-once made safe by re-derivation (nothing is replayed; the engine recomputes and suppresses by `content_hash`); normal speech is at-most-once.

**§7.6 Qualified consent.** `respond_permission` gains `span_start_ms`, `span_end_ms`, `asr_confidence` and `prompt_text_hash`, with gates in order: request open and ≤ 60 s → prompt hash matches → span starts after the prompt audio ended → **span does not overlap agent playback** → lexical whitelist → confidence ≥ 0.85 → **read-back confirmation**. The overlap gate is the definitive fix for *"hı-hı"*: the agent's own backchannel sits inside a playback interval, so a span overlapping it can never count as consent. Turkish normalisation maps dotted/dotless İ/I **before** `lower()`. A passing first response is `PROVISIONAL` until a second affirmative on a child request.

**§7.7 `flush_audio`.** Barge-in and RED cancel were measured agent-side while the client holds 60–200 ms in NetEq plus 15–40 ms output latency — so on RED the patient heard a **truncated non-RED sentence, then** the emergency script. The agent now sends `flush_audio` first, then cancels TTS, then waits ≤ 80 ms for `flush_ack`, then plays the RED clip. Clock sync every 5 s (median of 5 offset samples) so cross-boundary latency is computed in the client clock.

Consequently the **production p99 target for `red_first_audio_ms` is 600 ms**, not 300 ms; the 300 ms figure survives only as `red_decision_to_flush_issued_ms` measured agent-side. Both are catalogued with distinct ids so the four documents stop disagreeing.

---

## 8. Storage — the P0 requirement that makes deferring openEHR safe

What makes deferral safe is **not** openEHR. It is that answers are stored **per item, with stable slot ids, under an immutable versioned definition, with each answer's own timestamp**. Store a rendered blob or a denormalised score and retrofitting openEHR later is data archaeology; store items and it is a mapping exercise.

Four tables: `questionnaire_definition` (immutable, one row per compiled resolved protocol, carrying `resolved_protocol_hash`, `opt_template_id` and `opt_sha256`), `slot_definition` (the binding table, with `fhir_link_id` derived from `slot_id` **never a counter**, and `aql_path` **or** an explicit `openehr_deferred_reason` — a CHECK constraint forbids both being null, so absence is a decision rather than an oversight), `answer_revision` (append-only; a `UNIQUE` partial index enforces one live head per slot; a CHECK enforces that a non-self reporter cannot assert a SYMPTOM), and `coverage_snapshot` (materialised at finalisation for **every** slot including `not_asked`, which is what makes a coverage gap a stored fact rather than an absence).

Append-only is enforced at the **database**, not by discipline: column-level grants give the app role `SELECT, INSERT` plus `UPDATE (superseded_by, supersession_reason)` only, with a `BEFORE UPDATE` trigger raising on any other column.

*"Which questions was this patient actually asked, and why"* becomes one query. **openEHR would never have answered it** — `OPERATIONAL_TEMPLATE` has no `invariants` element and no predicate slot anywhere in its constraint tree.

### 8.1 The `.opt` binding validator

Generating an OPT is hard and Java-bound; **parsing one is an afternoon** — `Template.xsd` is 5 KB and frozen since 2010. The compiler emits only `slot → aql_path` bindings, and a pure-Python `lxml` walker validates every declared path against the committed `.opt`, asserting both resolution and `rm_type` match. `test_opt_is_pinned` asserts `opt_sha256` still matches the file, so re-authoring in Archetype Designer forces a new definition version and the binding-table diff is the review surface.

---

## 9. Runtime invariants

Invariants 1–11 stand as in `03 §4.6`, with **2 amended** (`get_work_status` → `cancel_work`) and **3 superseded by 19**.

| # | invariant | test |
|---|---|---|
| 12 | `protocol_next` is lock-free and never returns a torn `(version, next_step)` | Stall the state lane 10 s; 1000 concurrent calls return < 1 ms, self-consistent |
| 13 | No answer binds to a step `skip_if` invalidated; its transcript survives as unbound narrative | Hypothesis interleavings of utterances and commits |
| 14 | `answer_revision` is append-only; at most one live head per slot | `UPDATE … SET value_json` as the app role raises `InsufficientPrivilege` |
| 15 | Triage runs synchronously inside `apply_extraction` for every extraction | 500-turn corpus; `WorkType` has no triage member |
| 16 | Session triage never decreases without a `TriageRetraction` bound to an answered confirm | Property test over 1000 contradiction sequences |
| 17 | Every YELLOW terminates in `SPEAK_ACK` or `EXPIRED`, after walking the ladder | Patient talks continuously 200 s of fake clock |
| 18 | Expiry in a protected class is impossible without a committed note flag in the same transaction | Fault-inject 3 note-write failures; item stays `PENDING` |
| 19 | `preempt` is authorised by verified HMAC provenance, not shape | Seven-way forgery mutation test |
| 20 | LLM output is structurally disjoint from `TriageVerdict`; no extraction module reaches the signing key | `extra_forbidden` + import-boundary test |
| 21 | Background work cannot write slots; facts enter only as `ProposedFact` | `__init_subclass__` rejects a background `run` taking `StateContext` |
| 22 | `work_id` is content-addressed and survives restart unchanged | Crash mid-flight; same `work_id`, RED preserved, zero duplicates |
| 23 | Delivery phase is written ahead of the first audio byte; no content-hash duplicate renders | Crash at each of ~12 phases |
| 24 | Consent accepts only a whitelisted lexeme, above the floor, bound to the prompt hash, after read-back | Lexicon parametrisation incl. "hı-hı" |
| 25 | A span overlapping agent playback can never become consent | Play the backchannel clip, submit an overlapping "hı-hı" at 0.99 |
| 26 | On RED the flush precedes the clip; no non-RED sample renders > 120 ms after the decision | Simulated 200 ms NetEq |
| 27 | `base.life_threat` fires for every session regardless of branch or resolution failure | Golden corpus incl. `cluster.excluded` and a deliberately broken pack |
| 28 | `ClinicianOnlyDirective` is unreachable from patient summary, review cards and TTS | Type-graph closure over 4 roots + forced-injection serializer test |
| 29 | Any non-`SELF` instrument item yields `InstrumentNotScored`, never a number | Hypothesis over reporter assignments |
| 30 | Every slot appears in `coverage_snapshot`; `not_asked` renders as a gap, never a negative | Answer 3 of 12 ROS slots; assert 12 rows and "Sorulmadı" rendering |
| 31 | Every declared `aql_path` resolves in the committed `.opt` with matching `rm_type` | lxml walk, parametrised per slot |
| 32 | `cancelled` is reachable; RED seals the queue | Fire RED with two background items queued and one state item running |
