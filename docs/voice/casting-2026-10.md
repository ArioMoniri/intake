# Turkish voice casting, October 2026 (INT-449)

GitHub #762. The owner's feedback on 3 Oct 2026 was that George is an English voice speaking
Turkish, is "not the best Turkish voice of ElevenLabs", has intonation between words that "is not
fine", and lacks emotion. This document records how native Turkish candidates were found, rendered
and measured, and what the owner picked.

## The pick

On 3 Oct 2026 the owner picked **E04** from the round-2 blind page: "use E04 voice". This is D20 in
`files/00_STATE.md`, and it accepts the ADR-034 amendment
`docs/voice/adr-034-amendment-proposal-render-time-tags.md`.

| Item     | Value                                                                    |
| -------- | ------------------------------------------------------------------------ |
| Voice    | "Marcus - Warm, Clear and Professional" (Ozzano), `2PwDxni9MpXdYqgALrBh` |
| Model    | `eleven_v3`                                                              |
| Settings | Natural stability (0.5), style 0, default speed                          |
| Tags     | the closed per-context table, on the wire only                           |

E04 ranked fifth of the six rendered round-2 takes on the continuity figures. Its pitch range was
the widest (21.3 semitones). The owner chose by ear, as the method intended.

What the pick changed:

- `voice_clips.delivery` pins `CLIPGEN_VOICE_ID`, `eleven_v3` and the tags, and every row moves to
  v4. RED and instrument are at Robust (1.0) and never tagged, so RED stays the most stable delivery
  (invariant 21). E04's RED and instrument lines were heard at Natural, so the owner still owes one
  listen to a Robust take (amendment gate 7).
- The dev route speaks in the cast voice. The bundled dialogue set is re-rendered with
  `scripts/voice/render_cast_clips.py` (see `docs/evidence/INT-449.md`).

**The code key, now that the pick is made.**

Round 1 (`20261003T004143Z`, served v1 settings on v2, vendor defaults on v3, no tags):

- S01 Mine v2
- S02 Cavit v3
- S03 Eyüp v2
- S04 Meloxia v2
- S05 Eyüp v3
- S06 Ipek v3
- S07 Meloxia v3
- S08 Toprak v3
- S09 Yunus v2
- S10 Mine v3
- S11 Yunus v3
- S12 Aura v3
- S13 Ipek v2
- S14 Toprak v2
- S15 George v3
- S16 George v2
- S17 Cavit v2
- S18 Aura v2

Round 2 (`20261003T123356Z-r2`, all on v3 with tags; C = Creative 0.0, N = Natural 0.5):

- E01 Mine C
- E02 Marcus C
- E03 Toprak N (refused)
- **E04 Marcus N**
- E05 Gamze C (refused)
- E06 Cavit N (refused)
- E07 Gamze N (refused)
- E08 Cavit C (refused)
- E09 Meloxia C
- E10 Meloxia N
- E11 Mine N
- E12 Toprak C (refused)

## What was compared

**The pool.** The vendor's voice library was queried with `language=tr`, by one-year usage and by
clone count. That returned 341 Turkish-listed voices; no premade voice listed Turkish as its own
language. 312 were eligible. The 29 excluded were:

- 25 for a legacy custom rate, a cost multiplier the estimate cannot see;
- 2 English premade voices;
- 2 library voices whose own language or accent label is not Turkish.

**Eligibility** (`scripts/voice/voice_cast_library.py`) required all of these:

- a native accent: the voice's own language label is Turkish and no accent label is foreign;
- commercial use under the Voice Library terms on a paid plan, so no `famous` (iconic) voice,
  which has its own licence, and no custom rate;
- an adult voice.

**Scoring.** The eligible voices were scored on their metadata for a calm, warm, professional
delivery. The factors were:

- a standard (Istanbul) accent over a regional one;
- calm or warm descriptors, and none of the theatrical ones;
- a conversational or informative use case;
- a middle-aged or young-adult voice;
- a professional clone;
- Turkish verified on the pinned model;
- a notice period of a year or more;
- a usage signal.

**The shortlist.** The eight best scores were taken, four female and four male, and George was
added as the control. All eight have a 730-day notice period, no custom rate and no live
moderation.

| Voice (library name)                 | Voice id               | Gender | Age         | Accent   | Category     | Use case                |
| ------------------------------------ | ---------------------- | ------ | ----------- | -------- | ------------ | ----------------------- |
| Cavit, TV Presenter                  | `Q2IX97JeHBY3vNGzgM5s` | male   | middle-aged | istanbul | high_quality | informative_educational |
| Toprak, Balanced, Calm and Measured  | `pa0LgEk5MjYFGCuG6I3V` | male   | middle-aged | istanbul | professional | narrative_story         |
| Yunus, Charismatic Turkish Male      | `Q5n6GDIjpN0pLOlycRFT` | male   | young       | istanbul | professional | conversational          |
| Eyüp Tulûhan Etker, Deep and Rich    | `5HEFEBb9WCCpCdgZE77B` | male   | middle-aged | istanbul | professional | conversational          |
| Mine, Natural, Steady and Calm       | `8WPhqbK1tiExOyeiOUT0` | female | middle-aged | istanbul | professional | conversational          |
| Meloxia, Calm Professional Narration | `9Hlhs8vhmiUvbP4rTY7C` | female | middle-aged | standard | professional | narrative_story         |
| Ipek, Booming and Expressive         | `zCagxWNd7QOsCjiHDrGR` | female | middle-aged | standard | professional | informative_educational |
| Aura                                 | `jk1pqab9OzEmS07w0u2T` | female | middle-aged | istanbul | professional | informative_educational |
| George (control, the current voice)  | `JBFqnCBsd6RMkjVDRZzb` | male   |             | british  | premade      |                         |

**The models.** Each voice was rendered on two models:

- `eleven_multilingual_v2` under the served delivery table (`voice_clips.delivery`), which is the
  comparison that matters under ADR-034;
- `eleven_v3` with the vendor's default settings, for comparison only, because the vendor lists
  it for Turkish.

**The six lines.** These are catalogue text only, each checked at run time to occur verbatim in
its source. None carries a numeral or markup.

| Context         | Line                                                                                               | Source                                                    |
| --------------- | -------------------------------------------------------------------------------------------------- | --------------------------------------------------------- |
| welcome         | Hoş geldiniz. Muayenenizden önce size bazı sorular soracağım.                                      | `apps/mobile/src/lib/i18n/tr.ts` (INT-414 branch)         |
| routine         | Sizi bugün hekime getiren şeyi kendi sözlerinizle anlatır mısınız? Sözünüzü kesmeden dinleyeceğim. | `packages/protocols/base/intake.yaml`                     |
| sensitive       | Ailenizde bilinen bir hastalık var mı?                                                             | `apps/mobile/src/lib/i18n/tr.ts`                          |
| acknowledgement | Anlıyorum, devam edelim.                                                                           | `apps/mobile/src/lib/i18n/tr.ts` (INT-414 branch)         |
| instrument      | Sıradaki sorular standart bir ankete ait. Bu yüzden her zaman aynı şekilde sorulur.                | `apps/mobile/src/lib/i18n/tr.ts` (INT-414 branch)         |
| red             | Tek başınıza kalmayın; yanınızdaki kişiye durumu söyleyin.                                         | `files/protocols/base.life_threat.yaml` (exemplar do-not) |

This table records what these rounds rendered. On 16 Oct 2026 CD-111 (INT-468, applied by
INT-494) replaced the red line in the served rule with "Yanınızda biri varsa sizi yalnız
bırakmasına izin vermeyin.", and `scripts/voice/cast_turkish_voices.py` now carries that line, so
a later round renders the served text.

No validated instrument item is authored in this tree (`instruments.ts` refuses with
`items_not_authored`). For that reason the instrument context speaks the catalogue lead-in under
the instrument profile, and no item was invented.

**Spend.** 6,516 characters were sent: 9 voices, 2 models and 362 characters per voice per model.
That is 1.95 USD at the 0.30 USD per 1,000 characters planning rate, or about 0.52 USD at the
published 0.08 rate. The cap was 5 USD.

## The measurements

These are measurements of these takes, on the INT-449 casting corpus (the six lines above, run
`20261003T004143Z`, 3 Oct 2026). They are not properties of any voice or of the product (invariant
20). Word boundaries come from the vendor's own character alignment (the `with-timestamps`
response), so no boundary is guessed. The method is in `scripts/voice/voice_cast_report.py`.

Each take has 38 mid-phrase boundaries, which are word boundaries with no punctuation before them.
The figures are:

- **Gap.** The mean silence at a mid-phrase boundary, in milliseconds.
- **Jump.** The median absolute pitch change across a mid-phrase boundary, in semitones. It
  compares the last 60 ms of one word with the first 60 ms of the next. The 90th percentile is
  shown after the slash.
- **Rate CV.** The coefficient of variation of the per-word syllable rate across phrase-internal
  words. Lower means a steadier flow.
- **Syll/s and range.** The speaking rate in syllables per second, and the pitch range from the
  10th to the 90th percentile, in semitones. These are shown for context and are not ranked.

The rank is the mean of each row's rank on gap, jump and rate CV. Lower is steadier.

| Rank | Voice              | Model | Mean rank | Gap ms | Jump st (median / p90) | Rate CV | Syll/s | Range st |
| ---: | ------------------ | ----- | --------: | -----: | ---------------------: | ------: | -----: | -------: |
|    1 | Cavit              | v2    |      4.67 |      7 |             1.13 / 4.0 |    0.19 |   6.03 |      7.3 |
|    2 | Cavit              | v3    |      5.17 |      2 |             2.10 / 6.3 |    0.16 |   6.22 |      8.7 |
|    3 | George (control)   | v2    |      5.83 |      2 |             2.01 / 5.3 |    0.19 |   6.78 |     10.4 |
|    4 | Mine               | v3    |      6.50 |      9 |             1.11 / 4.3 |    0.19 |   6.21 |      9.5 |
|    5 | Toprak             | v2    |      7.00 |      9 |             1.36 / 5.2 |    0.19 |   6.03 |      7.5 |
|    6 | Yunus              | v3    |      7.00 |      3 |             1.92 / 6.0 |    0.20 |   7.42 |     14.4 |
|    7 | Meloxia            | v3    |      7.33 |      9 |             0.75 / 4.2 |    0.21 |   6.37 |     15.6 |
|    8 | Toprak             | v3    |      8.00 |      6 |             2.65 / 6.6 |    0.18 |   5.86 |     14.9 |
|    9 | Eyüp Tulûhan Etker | v3    |      8.67 |      1 |             2.12 / 9.4 |    0.22 |   6.81 |     16.5 |
|   10 | Mine               | v2    |     10.00 |      7 |             2.52 / 8.0 |    0.21 |   6.35 |     12.5 |
|   11 | George (control)   | v3    |     11.50 |      9 |             2.36 / 5.9 |    0.21 |   6.11 |     10.9 |
|   12 | Ipek               | v3    |     11.67 |     13 |             1.24 / 6.1 |    0.23 |   6.48 |     11.6 |
|   13 | Ipek               | v2    |     11.67 |     10 |             1.35 / 5.4 |    0.23 |   7.56 |     10.2 |
|   14 | Eyüp Tulûhan Etker | v2    |     12.00 |      2 |             3.83 / 6.7 |    0.24 |   7.17 |     11.8 |
|   15 | Meloxia            | v2    |     12.33 |     27 |             1.44 / 5.7 |    0.22 |   5.70 |     14.4 |
|   16 | Yunus              | v2    |     13.00 |      9 |            4.03 / 22.0 |    0.22 |   7.35 |     14.0 |
|   17 | Aura               | v3    |     13.83 |     11 |            1.54 / 11.1 |    0.25 |   6.04 |     16.7 |
|   18 | Aura               | v2    |     14.83 |     11 |             2.37 / 5.9 |    0.23 |   5.74 |      7.2 |

**How to read the measurements:**

- **They do not hear accent.** George on v2 ranks third. He joins words and moves his pitch about
  as smoothly as most of the native voices. What the owner hears in George is stress placement,
  vowel quality and Turkish phrase-final contour, and none of these figures measures them. The
  ranking separates the native voices from each other. It does not tell native from non-native,
  and the ear decides.
- **Gaps barely separate anyone.** Every take joins its words: the means are 1 to 27 ms, and
  almost no boundary breaks for 150 ms or more. Pitch jump and rate evenness carry the ranking.
- **The model matters per voice.** Cavit is steadiest on both models. Mine, Meloxia and Yunus are
  steadier on v3 than on v2. Toprak is steadier on v2. The pick is a voice and a model
  together.
- **Range is the nearest figure to emotion, and it is not ranked.** It is wider on v3 for most
  voices (Meloxia 15.6, Toprak 14.9, Eyüp 16.5 semitones) and narrowest for Cavit and Toprak on v2
  (about 7.5). A wide range is more expressive. It is also less even, which suits welcome and
  acknowledgement lines but not a RED line.
- **Yunus on v2 is not reliable.** Its 22-semitone 90th percentile, with the lowest voiced share
  in the run (0.54), points to octave errors in the pitch tracker. Its median is the figure to
  read.

## Round 2: eleven_v3 with render-time emotion tags (3 Oct 2026)

The owner's feedback on round 1 was "ElevenLabs could do better and more emotional". Round 2 used:

- **voices:** the four kept native voices, plus two more chosen from the library because their
  own descriptions claim expressiveness or emotion: Gamze Özdemir and Marcus/Ozzano;
- **model:** `eleven_v3` only, at Creative (0.0) and Natural (0.5) stability;
- **tags:** the closed per-context table, prepended on the wire only. RED and instrument carry no
  tag (see `adr-034-amendment-proposal-render-time-tags.md`).

The run is `20261003T123356Z-r2`.

**What rendered.** Six of the twelve combinations rendered, 36 takes in all: Mine, Meloxia and
Marcus, each at both stability levels. Every request from the fourth voice in render order
onwards (Gamze, Cavit and Toprak, at both levels) was refused with HTTP 401, after one call each.

- Cavit and Toprak rendered on v3 with the same key in round 1, so the refusal is not specific to
  those voices.
- A refusal that starts at one point in the run and then hits every later request fits an
  account-wide cause, most likely the key's or the account's character quota.
- The tool did not record the vendor's status token in this run. It now keeps it (for example,
  `quota_exceeded`), stops on the first 401, and can `--resume` a run, rendering only the missing
  takes under the same codes.

**Characters.** The run recorded 2,874 characters. Of these, 2,454 went to the 36 rendered takes;
the other 420 are the six refused welcome requests, which the tool counts conservatively but which
were not rendered.

**Tags.** No tag was read aloud as a word:

- Each tag's characters cover 64 to 293 ms of the vendor's alignment. That is shorter than any one
  of those words spoken.
- Where audio begins is in line with the untagged RED and instrument lines (0 to 0.11 s).
- The one exception to listen for is `[gently]` on the acknowledgement. In all six takes there is
  60 to 200 ms of sound before the first word, close to speech level. It may be an audible breath.

**Measurements.** These are measurements of these takes, on the same six lines. They cannot be
compared with round 1, whose settings differ. The rank is the mean of the ranks on gap, pitch jump
and rate CV, as in round 1.

| Rank | Voice   | Stability | Gap ms | Jump st (median / p90) | Rate CV | Syll/s | Range st |
| ---: | ------- | --------- | -----: | ---------------------: | ------: | -----: | -------: |
|    1 | Mine    | natural   |      7 |             1.75 / 8.8 |    0.18 |   6.05 |     11.4 |
|    2 | Meloxia | natural   |      8 |             1.76 / 5.5 |    0.22 |   6.23 |     14.8 |
|    3 | Marcus  | creative  |      1 |            1.93 / 19.5 |    0.24 |   5.94 |     20.6 |
|    4 | Mine    | creative  |      9 |             2.04 / 5.6 |    0.18 |   5.96 |     13.8 |
|    5 | Marcus  | natural   |      1 |            2.87 / 21.4 |    0.23 |   5.79 |     21.3 |
|    6 | Meloxia | creative  |      9 |             1.67 / 6.3 |    0.24 |   5.87 |     13.8 |

Marcus has the widest pitch range of either round, at 20.6 to 21.3 semitones. Its 90th-percentile
jump of about 20 semitones means large pitch swings, or octave errors in the tracker, so listen to
it for over-acting. Mine's range rose from 9.5 semitones on untagged v3 in round 1 to 11.4 to 13.8
here. Meloxia's stayed about the same, 13.8 to 14.8 against 15.6.

## Terms

The candidates are Voice Library voices used directly by id. They are not added to the account.
The vendor's library documentation says such voices may be used on a paid plan. It also says the
voice owner may withdraw a voice with notice, and every candidate has a 730-day notice period.
Commercial use of vendor-generated Turkish audio, including the voice identity, is still the
owner's open ask (a) in `docs/backlog/blockers.md` under INT-319 / ADR-028. The pick answers that
section's ask (c), the Turkish voice id, and nothing else.
