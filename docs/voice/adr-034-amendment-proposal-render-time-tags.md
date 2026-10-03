# ADR-034 amendment: eleven_v3 and emotion tags at render time only (INT-449)

Status: Accepted (owner decision, 3 Oct 2026; D20). The owner, Ario Moniri, picked E04 from the
INT-449 round-2 blind page in chat on 3 Oct 2026: "use E04 voice". The coordinator relayed the
pick. E04 is a render-time-tag take on `eleven_v3`, so the pick adopts this amendment. Proposed the
same day.

ADR-034 itself is on PR #734 and is not on main yet. When #734 merges, this decision is copied
into ADR-034's text and replaces its option (A) for the clip lane.

## Context

ADR-034 (Accepted, 3 Oct 2026) kept `eleven_multilingual_v2` for every context and did not adopt
audio tags. It rejected `eleven_v3` everywhere (its option D) on the premise that v3 has no
stability control, so RED could not be pinned as the most stable profile. It listed the conditions
a tag would have to meet: a closed per-profile table, prepended at the wire outside
`clip_text_hash`, never mid-item (`[pause]` included), never on RED or an instrument, and passing
the round-trip gate.

INT-449 cast native Turkish voices in two blind rounds. The owner's feedback on round 1 was:
"ElevenLabs could do better and more emotional". Round 2 auditioned `eleven_v3` with tags under
exactly ADR-034's conditions. The owner picked E04: "Marcus - Warm, Clear and Professional",
voice `2PwDxni9MpXdYqgALrBh`, on `eleven_v3` at Natural stability (0.5), tagged.

ADR-034's premise does not hold. The vendor's product guide documents three stability levels on v3
(Creative, Natural, Robust), and INT-449's renders were accepted at 0.0 and 0.5. RED can therefore
be pinned as the most stable profile on v3, at Robust (1.0).

## Decision

1. **One model, one voice.** `eleven_v3` for every context (`ELEVENLABS_MODEL_ID`), in the cast
   voice `CLIPGEN_VOICE_ID`. Every row of `voice_clips.delivery` is version 4, so no clip made
   under George or an earlier tuning is replayed.
2. **Settings as E04 was heard.** Natural stability (0.5), style 0 and the default speed for every
   tagged context. RED and instrument are Robust (1.0): the most stable profile, never tagged
   (invariant 21).
3. **Closed table, on the profile.** Each row carries its tags. `DeliveryProfile` refuses a tag on
   RED or an instrument, and any tag that is not one lowercase bracketed word, including
   `[pause]`.

   | Context         | Tags                      | Stability     |
   | --------------- | ------------------------- | ------------- |
   | welcome         | `[warmly]`                | Natural (0.5) |
   | routine         | `[calm]`                  | Natural (0.5) |
   | sensitive       | `[softly]` `[reassuring]` | Natural (0.5) |
   | acknowledgement | `[gently]`                | Natural (0.5) |
   | closing         | `[warmly]`                | Natural (0.5) |
   | RED             | none                      | Robust (1.0)  |
   | instrument      | none                      | Robust (1.0)  |

4. **On the wire only.** The ADR-028 gateway prepends the profile's `wire_prefix` to the request
   text, and nothing else ever carries a tag:
   - `text_tr`, the catalogue, the compiled packs and `clip_text_hash` never carry one;
   - `assert_speakable_tr` refuses any numeral before the wire (invariant 22);
   - the vendor normaliser stays off;
   - the words spoken are the script's, verbatim (invariant 10).

## The gates

| ADR-034 gate                                          | State                                                                                                                                                                                                       |
| ----------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1. The owner's decision, recorded                     | Done: this document and D20.                                                                                                                                                                                |
| 2. Model registry row and vendor-terms blocker        | Open. Hosted providers are declared in `infra/model-lanes/` with INT-428/INT-443, which are not on main. The vendor's commercial-use terms are still INT-319's ask (a) in `docs/backlog/blockers.md`.       |
| 3. Normaliser-off proven on v3 with a numeral fixture | Open as a vendor proof. Every request carries `apply_text_normalization: "off"`, and v3 accepted it in every INT-449 render. No numeral can reach the wire, because `assert_speakable_tr` refuses it first. |
| 4. The closed tag table, versioned                    | Done: `voice_clips.delivery`, v4 of every row.                                                                                                                                                              |
| 5. Round-trip ASR gate on the full compiled corpus    | Open. It has not been run. It is owed before the compiled packs' clips are built on v3.                                                                                                                     |
| 6. The owner's listening review                       | Done: the round-2 blind page, where E04 was picked.                                                                                                                                                         |
| 7. Same-voice check across contexts                   | Partly done. E04 was heard across six contexts, all at Natural. RED and instrument at Robust have not been heard; the owner should listen to one RED or instrument take.                                    |

## Consequences

- `DeliveryProfile` carries `voice_id` and `tags`, and the gateway sends the prefix from the profile,
  never from the caller.
- The dev route and the hosted clip lane take the voice and the model from the pins. The hosted lane
  is INT-443 (#775), which imports `ELEVENLABS_MODEL_ID` and defaults to the dev route's voice.
  #775 sends `text_tr` without the tag prefix, so it needs a one-line follow-up to send
  `profile.wire_prefix + text_tr`.
- INT-424 (#734) and INT-440 (#768) edit the same table or render under George. Whichever lands
  second takes v4 and the cast voice.
- This makes no accuracy, quality or naturalness claim (invariant 20). INT-449's figures are
  measurements of those takes.
