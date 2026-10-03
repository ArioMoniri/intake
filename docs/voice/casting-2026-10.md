# Turkish voice casting, October 2026 (INT-449)

GitHub #762. The owner's feedback on 3 Oct 2026 was that George is an English voice speaking
Turkish, is "not the best Turkish voice of ElevenLabs", has intonation between words that "is not
fine", and lacks emotion. This document records how native Turkish candidates were found, rendered
and measured, and how the owner picks one. The pick is the owner's. Nothing is pinned until it is
made.

## How to pick

1. Open `blind.html` from the run directory, `.cache/voice-cast/20261003T004143Z/`. It sits in the
   INT-449 worktree and is gitignored. Each row is one voice on one model under a code (`S01` to
   `S18`), in shuffled order. Every row speaks the same six lines.
2. Use **Play all** on a row to hear the six lines back to back. Listen for three things. Do the
   words join within a phrase? Does the pitch carry across word boundaries, or reset at each word?
   Does the voice sound calm and warm without being theatrical?
3. Send the code you would keep. You may send a first and a second choice. The control voice is
   one of the coded rows, so a pick against it is also a blind check of whether the change is
   worth making.
4. Do not open `labelled.html` until you have picked. It carries the names and figures.

The code key (which code is which voice and model) is not in this document while the pick is
open. It is in the run's `index.json` and `labelled.html`, and it is added here after the pick.

## What happens after the pick

- **A v2 code** (`eleven_multilingual_v2`) keeps the model ADR-034 accepted. The prepared change
  adds `CLIPGEN_VOICE_ID` to `voice_clips.delivery` and a `voice_id` field (the same in every row)
  to `DeliveryProfile`. It bumps every row's `version`, so no clip made in George's voice is
  replayed from a cache. The dev route's default voice moves to the pin. A near-miss test refuses
  a recording made under the George-era version of the same context.
- **A v3 code** (`eleven_v3`) is a model change. ADR-034 is amended with the owner's decision,
  and its gates 2 to 7 run before anything is served. Those gates are: the registry row and the
  vendor-terms blocker; normaliser-off proven with a numeral fixture; the closed tag table (empty
  if no tags); the round-trip gate; the owner's listening review, which this page is; and the
  same-voice check. The v3 renders here sent the five-field `voice_settings` and
  `apply_text_normalization: "off"`, and the vendor accepted both without error. That shows the
  request is accepted. It does not show the normaliser is off, because none of the six lines
  carries a numeral.
- **The bundled set is re-rendered** in the picked voice with `scripts/voice/render_bundled_clips.py`
  (INT-440). That tool pins its own voice constant, which moves to `CLIPGEN_VOICE_ID` in the same
  change once INT-440 is on main.

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

## Terms

The candidates are Voice Library voices used directly by id. They are not added to the account.
The vendor's library documentation says such voices may be used on a paid plan. It also says the
voice owner may withdraw a voice with notice, and every candidate has a 730-day notice period.
Commercial use of vendor-generated Turkish audio, including the voice identity, is still the
owner's open ask (a) in `docs/backlog/blockers.md` under INT-319 / ADR-028. The pick answers that
section's ask (c), the Turkish voice id, and nothing else.
