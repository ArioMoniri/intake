# ADR-034 amendment proposal: emotion tags at render time only (INT-449)

Status: Proposed (INT-449 round 2, 3 Oct 2026). The owner has not decided. ADR-034 itself is on
PR #734 and is not on main yet, so this proposal is kept here. When #734 merges, the owner's
decision on this proposal is copied into ADR-034's text, accepted or rejected. Until then,
nothing served uses a tag.

## Context

ADR-034 (Accepted, 3 Oct 2026) keeps `eleven_multilingual_v2` for every context and does not
adopt audio tags. It lists the conditions a tag would have to meet:

- it comes from a closed per-profile table;
- it is prepended at the wire, outside `clip_text_hash`;
- it never appears mid-item, `[pause]` included;
- it never appears on RED or an instrument;
- it passes the round-trip gate with no extra word and no sound effect.

INT-449 round 1 cast native Turkish voices on v2 and on v3 with no tags. The owner's feedback on
that round, on 3 Oct 2026, was: "ElevenLabs could do better and more emotional". Round 2
therefore auditions `eleven_v3` with tags under exactly the conditions above.

## Proposal

1. **Closed table.** Tags come only from `scripts/voice/voice_cast_tags.py` `TAGS`, one entry per
   delivery context:

   | Context         | Tags                      |
   | --------------- | ------------------------- |
   | welcome         | `[warmly]`                |
   | routine         | `[calm]`                  |
   | sensitive       | `[softly]` `[reassuring]` |
   | acknowledgement | `[gently]`                |
   | closing         | `[warmly]`                |
   | RED             | none                      |
   | instrument      | none                      |

   `check_table` enforces three rules: the table names the seven contexts, RED and instrument
   are empty, and every tag is one lowercase bracketed word that is not `[pause]`. Changing the
   table is a reviewed change with a version bump.

2. **On the wire only.** The request layer (`request_body`, `synthesise_aligned`) prepends the
   context's tags to the request text, and nowhere else:
   - `text_tr`, the catalogue, the compiled packs and `clip_text_hash` never carry a tag;
   - `assert_speakable_tr` and the markup gate keep running on the catalogue text, so a tag
     cannot be authored into a line;
   - the wire text, tags included, also passes `assert_speakable_tr`;
   - a prefix that is not the table's own for its context is refused before the wire, and so is
     any prefix on v2.

   The spoken words are therefore the catalogue's, verbatim (invariant 10).

3. **Measured, not assumed.** Each take records the audio span the vendor's alignment gives the
   tag characters (`tag_ms`). A tag read as direction covers about 0 ms. A tag that was spoken, or
   rendered as a sound, covers more, and that take fails the proposal.

## Gates before anything is served

These are ADR-034's gates, unchanged, in its order:

1. the owner's decision on this proposal, recorded in ADR-034;
2. the model registry row and the vendor-terms blocker for `eleven_v3`;
3. normaliser-off proven on v3 with a numeral fixture (round 1 shows only that the request is
   accepted);
4. this closed table, versioned;
5. the round-trip ASR gate on the full compiled corpus, with no extra word and no sound effect;
6. the owner's listening review, which is INT-449 round 2's blind page;
7. the same-voice check across contexts.

RED stays pre-positioned, untagged and on the most stable profile on any model (invariant 21).

## Consequences

If accepted:

- `DeliveryProfile` carries a model id and a tag tuple per row;
- the ADR-028 gateway sends the prefix from the profile and never from the caller;
- the clip key includes the profile version, so a tag change re-synthesises.

If rejected, the round-2 renders remain an audition and nothing changes.

Either way, this proposal makes no accuracy, quality or naturalness claim (invariant 20). Round
2's figures are measurements of those takes.
