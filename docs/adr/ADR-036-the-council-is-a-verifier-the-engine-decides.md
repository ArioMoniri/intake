# ADR-036 · The council is a verifier, and the deterministic engine decides

Status: Accepted (owner decision, 3 Oct 2026, in chat: "im giving u approval"). It narrows the owner's request of 2 Oct 2026 on the advice of two binding challenger reviews (INT-430, GitHub #732).

## Context

The owner's request of 2 Oct 2026, verbatim:

> "the structure should be dynamically asking question with regard to previous questions patients docs added and answers to previous question and so on as described also in roadmap with any model could be an agent council which should work both with on prem and with api models"

The first design followed the request literally. Four roles (extractor, document reader, follow-up proposer, critic) would vote, a majority would fill slots, and a ranker would reorder the pack's eligible questions. Two strict challenger reviews of INT-428/INT-430, one medical and one AI/ML, were made binding by the coordinator on 2 Oct 2026. Between them they found five problems with that design.

- **A majority can be wrong.** Several models voting "absent" on a red-flag slot are not more likely to be right. Their errors are correlated: the same ASR transcript, the same Turkish negation ("olmuyor değil", "yok gibi"), the same training data. A vote that clears a red flag is a missed RED.
- **Reordering fights the engine.** A runtime ranker moves questions the pack authored in a clinical order. files/13 §9.2 makes interleaving *emergent* from gates ("nobody writes an interleaving rule"); a ranker writes one.
- **Late answers are dangerous.** A council slower than the primary extraction can overwrite an answer the patient has just given, or land after a RED, or land after the session has ended.
- **Hosted models on the PHI path.** Per invariant 19, a transfer-basis escape hatch is not enough; the hosted lane must be unrepresentable there.
- **Confidence numbers are uncalibrated.** Self-reported confidence and multi-member agreement have never been measured on this corpus. Treating either as a threshold is an accuracy claim nobody measured (invariant 20).

## Decision

**1. The council verifies; it does not decide.** The primary single-pass `extract_slots` handler still binds every answer, under the engine lock, and that binding is what triage reads, so RED never waits on a model. Only *after* the bind does the handler call `VerificationSink.request_verification`. That call appends to a bounded queue and returns. The verifier (`services/voice-runtime/src/intake_voice_runtime/clinical_agent/council/`) runs later as Backend Work on the event loop.

**2. The deterministic IntakeEngine stays the only authority on the next question.**
- The verifier can do exactly one thing to the agenda: ask the engine to *append* a scripted re-entry to a slot that has already been answered (`IntakeEngine.append_verification`).
- The engine appends only at the slot revision the verifier read. This is a compare-and-swap, so a patient who corrected the answer in the meantime wins.
- The text is the slot's own: `ask_tr` to re-ask the positive question, or `confirm_tr` for a numeric confirm-back. Nothing is improvised (invariant 10).
- The append shares files/13 §11.1's limit of two attempts per slot.
- The engine never skips, reorders, binds or clears anything because of the council.
- Per the medical review, a delta pre-fill never offers a red-flag or tense-anchor slot as a confirm step, so a "yes" can never clear a red flag.

**3. The verifier's scope is set by the served pack, and enforced by type.** The verifier reads only:
- slots that some red-flag `when` predicate reads (pack rules and `base.life_threat` alike);
- numeric slots.

Excluded:
- tense anchors, which are asked as a scripted closed choice and are never read by the council;
- `text_only` slots, the files/13 §13 mark for safeguarding content;
- identity slots;
- instrument items. These are not slots, so they have no ref.

The member output schema enumerates only the in-scope refs. A reading for any other ref is dropped before adjudication.

**4. The adjudication rule is deterministic and asymmetric** (`council/adjudicate.py`). The verdict is a pure function of the readings and the slot views.

| Slot state | What the readings say | Action |
|---|---|---|
| Red-flag slot, answered **absent** directly | *Any one* draw reads present, hedged, intermittent, double-negated, qualified or does-not-know | `REASK_POSITIVE`; the field is CONTESTED and the worst case stands for the clinician |
| Red-flag slot, answered **present** | Readings that disagree | Nothing. No count of "absent" readings clears anything, and the action set has no member that could |
| Red-flag slot, not yet asked, gate **open** | Arming narrative evidence | Recorded as narrative provenance only. The step is asked in its authored place; asking it early would be the reorder both reviews removed |
| Red-flag slot, gate **closed**, or already a gap | Arming narrative evidence | An add-only, coded `CANDIDATE_FLAG` for the clinician. `LlmCandidateTriage` caps it at YELLOW_REVIEW (invariant 1) |
| Numeric slot with a bound value | Any draw gives a different number, or reads absent, hedged or unsure | `CONFIRM_BACK` (D13's scripted confirm-back). The bound value stays |

How readings are handled:
- **No self-reported confidence.** The schema has no field for it, and a document that adds one is refused whole.
- **Verbatim evidence.** Every reading quotes its evidence verbatim (`quote == transcript[start:end]`); anything else is dropped.
- **Turkish hedging is an enum.** "Plain absent" is the only reading that does not arm.
- **Clinician-only outputs.** Candidate flags and contested values go to the clinician's record (`VerifierLedger`), never to the patient's device. Each field carries its provenance: direct, narrative, document, contested or *Sorulmadı*.

**5. Latency budget.** The council never blocks a turn, and the Talker never awaits it (invariant 9). The guarantees come from structure, not from tuning:
- The sink is synchronous O(1), and the verifier holds the engine lock only through a non-blocking acquire to read views.
- Verdicts apply through the ordinary state lane (`plan_follow_ups`), FIFO after the extraction they verify and behind the RED seal.
- A round ends at a deadline on the injected clock; any draw still running is cancelled and abstains.
- A process-wide `AdmissionGate` sheds a verification when it is saturated, rather than letting it queue behind the primary lane.
- Each verification is an *elective* charge, so it is refused outright while HB-O8 leaves the cap undeclared.
- A fake-clock test stalls the members for 30 s. Talker turn latency, the asked order and a rules-engine RED all stay identical to the council-off run.
- A verdict that lands after the session ends, or after a RED sealed the queue, is not applied. It becomes a clinician-inbox addendum, and triage is re-run anyway.

**6. Self-hosted and API parity.** Every member resolves as role `llm.council.<member_id>` through INT-428's lane router (ADR-035, hosted model lanes).
- **Pinning.** A member is pinned once per session. Later drift is refused, and a mock route is unrepresentable.
- **Hosted members** exist only on a synthetic deployment. On a real-PHI deployment, or one with no data class set, the pin returns a self-hosted member or refuses, and there is no transfer-basis branch.
- **Hash binding.** The policy binds each member by the hash of (provider, `model@revision`, weights digest, prompt version, decoding, slot types). A model swap cannot inherit a calibration made on another model.
- **One request body.** Self-hosted (vLLM/SGLang) and hosted members receive the same OpenAI-compatible body. Only the destination differs, and that is the router's decision, outside `clinical_agent`, which imports no network client.
- **Prefix cache.** Each session carries its own `cache_salt` for the shared prefix cache. The salt is kept out of the recording key, so CI replays recordings across sessions and never re-runs a model. A recording made on another lane is refused.

**7. Members.** The default mode is same-model self-consistency (one member, k draws) plus the D13 confirm-back. Multi-member mode cannot be represented until an error-independence study and a calibration study are committed under `docs/evidence/`, each with a date and a named corpus. Even then, the records state that the measurement happened, never a figure (invariant 20). The admin console picks the members, and four-eyes approval is enforced through `admin/flag_governance.py` (split row).

**8. Cut, and where each part went.**
- The free follow-up ranker becomes an offline Loop-2 `yield_table` proposal: DETAIL steps only, within one section, covered by the pack hash (split row, `services/learning`, proposal-only per invariant 12).
- The critic is cut.
- The document reader stays the existing `parse_document` Work. The medical review's document rules (add or arm only, undated items not slot-eligible, staleness windows, identity match before extraction, document vs patient becomes CONTESTED) belong to that path (split row).

## Physician decisions

The verifier as built needs none of these decisions: its asymmetric default is the safe direction. All eight await clinical sign-off. INT-432 is creating the register for them (`packages/protocols/decisions/CD-NN.yaml`, status `draft_needs_source`), and an unsigned value reads as absent and fails closed.

1. **CD-02.** Which slots the council may never fill, even after confirmation.
2. **CD-03.** Whether a narrative PRESENT fires RED directly, or only arms the probe.
3. **CD-04.** The per-rule table mapping each Turkish hedge to an answer state.
4. **CD-05.** The tense-anchor choice set for each RED rule.
5. **CD-06.** The staleness window for each document class.
6. **CD-07.** The per-session ceiling on numeric confirm-backs. While unsigned there is no session cap, red-flag re-asks are never capped, and each slot keeps its two attempts.
7. **CD-08.** Who receives a YELLOW_REVIEW candidate flag, and within what SLA.
8. **CD-09.** The red-flag extraction sensitivity floor, with the golden set a lane swap must pass.

## Consequences

- **The owner's request is met in its safe part.** Earlier answers already drive which questions are asked, through the gates. Narrative and documents now drive *re-asks*, *confirm-backs* and *clinician flags*. The order of the questions is still the pack's.
- **The literal reading is moved, not dropped.** A council that ranks the next question and fills slots by vote becomes a Loop-2 proposal and is gated on studies. The owner accepted that narrowing on 3 Oct 2026.
- **The engine gained** a per-slot revision counter, a compare-and-swap `append_verification` and rebinding verification re-entries. `delta` gained a list of slots it will not pre-fill (`safety_full_ask_fact_keys`). The `ExtractSlotsHandler` gained an optional `verifier` sink. With the default `None`, every session composed today runs exactly as it did.
- **`StateEffect` still has no `candidate_flags`.** The state lane carries no LLM material (files/12 §7.4), so verifier flags go to the clinician ledger.
- **Production wiring is a split row.** The verifier is not yet composed into a production session. Composing it needs the INT-428 router adapter, a triage re-run binding, a clinician-inbox sink, the INT-432 CD-07 binding and an answer to HB-O8. Until then it fails closed, which here means it is absent.
- **Signals:** `council_member_latency_ms`, `council_member_tokens_total`, `council_member_agreement_total`, `council_verifications_total`, `council_actions_total`, `council_readings_dropped_total`, and `llm_trace_spans_emitted_total{kind="verification"}`.
- **Enforced by** `tests/voice/test_council_contract.py`, `test_council_adjudication.py`, `test_council_lanes.py`, `test_council_timing.py` and `test_council_ledger.py`. Each must-have test carries a near-miss control.
- Recorded against files/10 §9 row `llm-boundary`.
