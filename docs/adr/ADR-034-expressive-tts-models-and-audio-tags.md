# ADR-034 · Expressive TTS models and emotion audio tags on the offline clip lane

Status: Accepted (owner decision, 3 Oct 2026; INT-424, GitHub #719, PR #734). The owner, Ario
Moniri, decided in chat on 3 Oct 2026: "eleven labs is yes". The coordinator relayed the decision
to this PR. Option (A) is adopted: the pinned model stays `eleven_multilingual_v2` for every
context, and audio tags are not adopted. Proposed 2 Oct 2026.

## Context

The owner wants the scripted questions to sound more natural and emotionally attuned while
staying medical and professional. INT-424 retunes the five `voice_settings` of the pinned model
(delivery profiles v2) and adds a gate that refuses markup inside scripted text. The open question
is whether an expressive model would do more. That would be `eleven_v3`, or `eleven_v4`, released
28 Sep 2026, using emotion **audio tags** such as `[warmly]` or `[pause]`.

The vendor's own pages were retrieved on 2 Oct 2026 and are cited in `docs/evidence/INT-424.md`.
They say four things that matter here:

- **Controls.** On `eleven_v3`, style is the only voice setting; stability, similarity, speaker
  boost and speed are unavailable. On `eleven_v4`, stability and similarity remain; style and
  speed are unavailable. `eleven_multilingual_v2` keeps all five. Neither expressive model reads
  SSML. Both take bracketed audio tags written inline in the text.
- **Reliability.** Tags "may be interpreted as a request for a sound effect rather than a delivery
  instruction". Experimental tags "may be less consistent across different voices". Emotion
  written as narrative prose is spoken aloud.
- **Use.** `eleven_v3` is not meant for real-time use. Turkish is listed for all three models.
- **Price.** API pricing is 0.08 USD per 1,000 characters for Multilingual v2 and v3 alike.

The lane is bounded by ADR-028: offline clip generation of the fixed set only. A profile tuned
for another model is refused before the wire (`DeliveryProfileMismatchError`).

## Decision

**We keep `eleven_multilingual_v2` for every context and do not adopt audio tags.**
Naturalness comes from the v2 delivery profiles and from punctuation in device-composed lead-in
copy only. Measured against the binding rules, it looks like this:

| rule                                           | what an expressive model would need                                                                                                                                                                                                                                                                                                                                                                                                              |
| ---------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Invariant 10 (verbatim)                        | A tag is a word the protocol did not author. It can never sit inside `text_tr`; the INT-424 gate refuses `<`, `>`, `[`, `]` there. Any tag would come from a closed per-profile table, be prepended at the wire outside `clip_text_hash` (the VoxCPM2 instruction rule in `docs/voice/on-prem-tts-wiring.md` §3), and pass the round-trip ASR gate with no extra word and no sound effect. A tag mid-item, `[pause]` included, is never allowed. |
| Invariant 21 (RED)                             | RED must be the most stable profile. `eleven_v3` has no stability control, so RED cannot be pinned most-stable there and stays off it. RED and instrument never carry a tag on any model. RED stays pre-positioned and never fetched.                                                                                                                                                                                                            |
| Invariant 22 (numerals)                        | The compiler's expansion must be the only one that runs. A model is admissible only if its normaliser can be switched off (`apply_text_normalization: "off"`) and the switch is proven with a recorded fixture. The SSML break carries a duration numeral, and the gate refuses it.                                                                                                                                                              |
| One voice per session (files/03 §4.9.1 row 11) | Mixing models across contexts can change timbre for the same voice id. A mixed table must pass a same-voice listening check before it ships.                                                                                                                                                                                                                                                                                                     |
| ADR-028 and latency                            | The cached path costs 0 ms of TTS at runtime on any model (files/03 §4.5), so the model choice is a build-time cost. Only the INT-326 dev on-demand route would feel `eleven_v3`'s latency, and it never runs in production.                                                                                                                                                                                                                     |

The options considered:

- **(A) Stay on Multilingual v2 with tuned profiles.** Adopted.
- **(B) Use `eleven_v3` for welcome, acknowledgement and closing only, with tags from a closed
  table.** Possible after the gates below. Its cost is losing speed and stability on those
  contexts.
- **(C) Use `eleven_v4` everywhere.** This loses speed, which sensitive, instrument and RED use,
  and style.
- **(D) Use `eleven_v3` everywhere.** Rejected under invariant 21.

(B) and (C) are not adopted. Reopening either is a new decision, and these gates come first, in
this order:

1. Amend this ADR with the owner's new decision.
2. Record the model registry row and the vendor-terms blocker for the new model.
3. Prove normaliser-off with a fixture.
4. Add the closed tag table with a version bump.
5. Pass the round-trip gate on the full compiled corpus.
6. Run a sample render under 5 USD with `scripts/voice/render_delivery_samples.py` and the owner's
   listening review.
7. Pass the same-voice check.

## Consequences

Nothing switches model under this ADR, and no code depends on it. The markup gate it relies on is
already enforced: `assert_speakable_tr` raises `MarkupInScriptError`, and the dev route answers
422 `not_speakable`. Tests cover it in `tests/voice/test_elevenlabs_clipgen.py` and
`tests/api/test_dev_voice_george.py`. So a tag can reach the vendor only through a reviewed
change to that gate, never through a copy edit.

Option (B) would make the delivery table carry two model ids, so `DeliveryProfile.model_id` would
stop being uniform. The gateway would then select per profile instead of refusing. That is a
change to the ADR-028 adapter, reviewed under the `cloud-clipgen` threat row.

This PR writes no `files/00_STATE.md` §3 row. Decision ids there are allocated centrally, so the
row is the coordinator's to add, as for ADR-033. No accuracy, quality or naturalness claim is made
(invariant 20). The sample measurements are in `docs/evidence/INT-424.md`.
