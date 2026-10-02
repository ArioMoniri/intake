# Wiring the delivery profiles to the self-hosted `residency_tr` TTS

Status: guide (INT-415, 27 Sep 2026). Nothing in this document is wired yet. The profiles
already drive the ElevenLabs clip lane (ADR-028 offline build and the INT-326 dev route). This
guide says how to give the same seven profiles to the self-hosted TTS that `residency_tr`, the
one production voice profile, actually runs. It names only models pinned in files/03 §4.9.1,
and it makes no quality, WER or MOS claim (invariant 20).

## 1. What a delivery profile is

Every spoken utterance carries one **delivery context**
(`apps/mobile/src/lib/dialogue/deliveryContext.ts`):

- `welcome`
- `routine`
- `sensitive`
- `instrument`
- `acknowledgement`
- `red`
- `closing`

The server maps the context to a **profile** (`packages/voice-clips/src/voice_clips/delivery.py`),
a versioned row whose key `delivery.<context>@v<version>` is part of every clip cache key. Three
rules hold on every lane, whatever the model:

1. **A profile changes how the words are said, never which words.** The spoken text is the
   scripted `text_tr`, verbatim (invariant 10), numerals already expanded (invariant 22). No
   profile may add, drop or reorder a word.
2. **A profile never changes whose voice it is.** One voice per session (files/03 §4.9.1 row 11).
   On ElevenLabs the identity knobs (similarity, speaker boost) are equal across profiles; on
   the self-hosted models the voice id, reference audio and seed stay fixed.
3. **`red` and `instrument` are the most stable and carry no expressive styling.** RED audio is
   pre-positioned on the device and triggered over the data channel (invariant 21). It is never
   fetched on demand.

The intent of each profile, independent of any vendor:

| context           | intent                                                           |
| ----------------- | ---------------------------------------------------------------- |
| `welcome`         | The warmest: natural variation, a little expressive, unhurried   |
| `routine`         | Calm and neutral; professional after the opening                 |
| `sensitive`       | Steadier and slower than routine, no expressiveness added        |
| `instrument`      | Very stable, no styling, slightly slower; validated item wording |
| `acknowledgement` | Brief and warm; never slower than routine                        |
| `red`             | The most stable of all, no styling, clear rather than rushed     |
| `closing`         | Warm like the welcome, a touch steadier                          |

## 2. The controls each pinned model actually has

`residency_tr` TTS is files/03 §4.9.1 rows 10–12. Row 13 (`ResembleAI/chatterbox`) is held,
not scheduled, and is not wired here.

### VoxCPM2 — rows 10 and 11, the primary (cached-clip and dynamic path)

The registry row is `voxcpm2-tts`: `openbmb/VoxCPM2@32279eff…`, served through `voxcpm==2.0.3`.
Its controls come from the OpenBMB/VoxCPM README (retrieved 27 Sep 2026). Re-check them against
the pinned package before wiring.

| control                                                                                                                                                          | what it does                                                                                          | use for delivery                                                                                                                |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| **style instruction** — a description in parentheses at the start of `text`, e.g. `(calm, gentle tone)`; also works with a cloned voice ("controllable cloning") | Steers speed, emotion and style in natural language                                                   | **The main delivery knob.** It is the only way to ask for "slower" or "warmer": there is no numeric speed parameter             |
| `cfg_value` (default 2.0)                                                                                                                                        | Guidance scale: lower allows more improvisation; higher follows the instruction and text more closely | Keep 2.0 at cut-over. Move it only if the listening test asks, and then one profile at a time                                   |
| `inference_timesteps` (default 10)                                                                                                                               | Quality against latency                                                                               | **Identical on both tiers.** A different setting between the cached and dynamic paths risks an audible voice change mid-session |
| `seed`                                                                                                                                                           | Reproducible generation                                                                               | Pin one seed for the whole voice, so a rebuilt clip is the same clip                                                            |
| `reference_wav_path` / `prompt_wav_path` + `prompt_text`                                                                                                         | Voice cloning                                                                                         | The **voice**, not the delivery. Fixed per voice id and never varied by profile                                                 |
| `normalize`                                                                                                                                                      | The built-in text normaliser                                                                          | **Always `False`.** It routes Turkish to the English branch (files/03 §4.9.6). Invariant 22                                     |

With no instruction the model "infers a fitting speaking style based on the text itself". That
is exactly what `red` must not do: inferring from an alarming sentence risks an alarmed
delivery, which is "alarming beyond the triage action". So RED gets an explicit steady
instruction, not the model's own inference.

### Freya-TTS small — row 12, the whole-session fallback

The registry row is `freya-tts`: `freyavoice/Freya-TTS@d124e07`, with code pinned at `146d36c`.
The README at that commit documents `synthesize(text, steps=32, seed=LEYLA_SEED)` and says the
model "conditions only on text". It has no speaker embedding, speed, pitch, emotion, style or
guidance control.

- **Every profile renders identically on Freya.** That is acceptable, because Freya is selected
  at session start as a whole-session fallback and the session then speaks neutrally throughout.
- **`seed` is the voice** (the initial noise _is_ the speaker), so it stays pinned to Leyla.
  Varying it per profile would change the speaker mid-session, which rule 2 forbids.
- **Do not fake delivery with post-processing** (time-stretch, pitch shift). That alters audio
  the model did not produce, and no round-trip gate covers it.
- The normaliser stays off. The bridge calls `_synth(text, do_norm=False)` and rejects any digit
  (docs/runbooks/team-gpu-server.md).

## 3. The mapping

These are **candidate** values for the listening test in §7. They are voice tuning, not
clinical values, and the owner's listening review decides them. Write instructions in English,
as every README example is. Whether a Turkish instruction works better is itself a listening-test
question.

| context           | ElevenLabs v1 (live today) stability / style / speed | VoxCPM2 style instruction (candidate)       | VoxCPM2 `cfg_value` | Freya   |
| ----------------- | ---------------------------------------------------- | ------------------------------------------- | ------------------- | ------- |
| `welcome`         | 0.40 / 0.20 / 0.98                                   | `(warm, friendly, unhurried)`               | 2.0                 | neutral |
| `routine`         | 0.55 / 0.05 / 1.00                                   | `(calm, neutral, clear)`                    | 2.0                 | neutral |
| `sensitive`       | 0.65 / 0.00 / 0.92                                   | `(calm, gentle, slightly slower)`           | 2.0                 | neutral |
| `instrument`      | 0.80 / 0.00 / 0.95                                   | `(steady, neutral, clear, slightly slower)` | 2.0                 | neutral |
| `acknowledgement` | 0.48 / 0.15 / 1.02                                   | `(warm, brief)`                             | 2.0                 | neutral |
| `red`             | 0.85 / 0.00 / 0.95                                   | `(steady, clear, calm)`                     | 2.0                 | neutral |
| `closing`         | 0.42 / 0.20 / 0.97                                   | `(warm, friendly)`                          | 2.0                 | neutral |

Every ElevenLabs row also carries `similarity_boost` 0.75 and `use_speaker_boost` true, on
`eleven_multilingual_v2`.

Rules for the instruction strings:

- **A closed table, never composed.** The instructions live beside the ElevenLabs settings in
  `voice_clips.delivery`, as a field of the same versioned profile. Changing an instruction bumps
  the profile `version`, and so re-keys the clips. Nothing at runtime builds an instruction, and
  no patient word can reach one.
- **Numeral-free, like the text.** `assert_speakable_tr` must run over the instruction as well as
  the text. "No numeral reaches any TTS model" covers every character the model reads.
- **Outside the hash.** The clip manifest hashes `text_tr` alone (`clip_text_hash`). The
  instruction is prepended by the adapter at the wire, so the compiler's `text_hash` and
  `clip_id` never change. The profile key in the object key is what separates two deliveries.
- **A spoken instruction is a build failure.** A model that reads the parenthesised text aloud
  has changed the words. The compile-time round-trip gate (files/03 §4.9.6) must catch it: the
  independent ASR transcript must equal the expanded `text_tr` with no extra words.

## 4. The adapter interface

The seam is `voice_clips.gateway.TtsGateway` (ADR-006):

```python
def synthesise(self, *, text_tr: str, voice_id: str, profile: DeliveryProfile) -> SynthesisedSpeech
```

`profile` is required with no default, so every caller already states the delivery.

- `ElevenLabsClipGenGateway` sends `profile.voice_settings` today.
- `HttpTtsGateway` is the self-hosted adapter for the offline build, and the one to change. It
  accepts the profile and sends `{text, voice_id}` exactly as before, because the `/synthesize`
  contract has no delivery field. A test pins that body.

To wire it:

1. Add a `self_hosted` block to `DeliveryProfile` (instruction, `cfg_value`), validated at
   construction the way the ElevenLabs settings are. Bump every row's `version`.
2. Extend the `/synthesize` body with an explicit, closed field, for example
   `{"text", "voice_id", "delivery": {"profile", "instruction", "cfg_value"}}`.
   - The bridge prepends the instruction and calls `generate(..., normalize=False)`.
   - It rejects any digit in text or instruction, and any unknown field.
   - It never composes an instruction of its own.
   - The bridge (`work/tts_server.py` on the serving host) is not in this repository today, so
     its change is an ops change with its own evidence file.
3. Freya's bridge accepts the same body and ignores `delivery`, by design, since it has no
   controls. Its response must be byte-identical with and without the field; test that.
4. **The dynamic path** (row 11) runs through `intake_voice_runtime.ports.SpeechSynthesizer.synthesize(text_tr, voice_id)`
   and needs the same profile argument. That change is under `services/voice-runtime`, so the
   `runtime-reviewer` reviews it.
   - The Talker's six tools do not change (invariant 9). The profile is an argument of the
     synthesizer port, not a tool.
   - A RED result never reaches this path: it plays the pre-positioned script.
5. Recorded fixtures: `RecordedTtsGateway` already honours a recording's `delivery_profile`, so
   each self-hosted take is recorded under its profile key once the lane has controls.

## 5. Registry fields (invariants 13, 14, 19)

Every model on the PHI path has a row in `observability/registry.yaml` before it serves.
`voxcpm2-tts` is the worked example:

| field                                                              | meaning                                                                 | `voxcpm2-tts` today                               |
| ------------------------------------------------------------------ | ----------------------------------------------------------------------- | ------------------------------------------------- |
| `model_id` + `revision` + `weights_sha256`                         | `model_id@revision + sha256`, per weight file                           | `openbmb/VoxCPM2` @ `32279eff…`, two files hashed |
| `licence_verified_at` + `licence_blob_url` + `licence_blob_sha256` | Read from the raw LICENSE blob, never a badge or card tag               | 2026-08-29, the OpenBMB/VoxCPM blob at `272b8ff…` |
| `self_hostable` / `self_hosted_now`                                | Open weights, running on our host                                       | true / true (dev host, CPU today)                 |
| `probe` + `budget_ms`                                              | The synthetic probe and its budget                                      | `http_health`, 3000                               |
| `fallback`                                                         | What serves if this fails                                               | `component:freya-tts`                             |
| `phi_path`                                                         | On the PHI path, so CI fails the release without a licence verification | true                                              |

The profiles add **no** registry row: a delivery profile is configuration of an existing model,
not a model. Changing the pinned model or its revision is a registry change and an ADR.

**Finding for the cut-over.** The `freya-tts` row carries a licence string and a probe, but no
`model_id`, `revision`, `weights_sha256` or `licence_verified_at`. The runbook records that the
Freya weights repo has no LICENSE blob. Because it is the named fallback on the PHI path, its row
must be completed before `residency_tr` serves patients. This is not caused by the profiles, but
the cut-over is where it bites.

## 6. The clip manifest and the Turkish orthography gate (invariants 10 and 22)

- The compiler writes `packages/protocols/dist/<pack>/clips.<locale>.<voice>.json`.
  - Each row carries `text_tr`, `text_hash = clip_text_hash(text_tr)`, a
    `clip_id = sha256(text, voice, locale)`, `scripted` and `subject`.
  - Every digit, unit, dose form and drug name is expanded to Turkish orthography **before** the
    hash (`protocols.compile.number_expansion`).
- `make clips VOICE=<voice>` (`voice_clips.build`) reads each row's context from its subject:
  - `rf.*` → `red`;
  - `<InstrumentId>.<item>` → `instrument`;
  - a slot → `routine`.

  It then synthesises under that profile and stores
  `clips/<locale>/<voice>/<profile key>/<clip_id>`.

- A self-hosted voice has its own voice id, so its clips never mix with George's.
- A version bump is a cache miss that re-synthesises. `--force` is only for a changed model
  under a stable voice id.
- `load_clip_manifest` refuses a row whose text no longer hashes to its key. That tamper control
  is unchanged.
- Welcome, closing, acknowledgement and sensitive lead-ins are composed on the device (INT-414)
  and are not compiled manifest rows. They reach the self-hosted lane through the device's
  per-sentence synthesis (`apps/mobile/src/lib/dialogue/ttsLane.ts`). Its synthesizer takes the
  text alone today, so wiring the dynamic path (§4 step 4) is also where the device starts
  passing the context.
- Invariant 22 holds on every layer:
  - the compiler expands;
  - `assert_speakable_tr` refuses any Unicode number character before the wire;
  - the model's normaliser is off;
  - the bridge rejects digits;
  - the compile-time round trip (synthesise, transcribe with an independent ASR, diff against
    the expansion) fails the build on mismatch.

  Run the round trip **per profile**, because an instruction can change what is spoken.

## 7. Latency budget

- **The cached-clip path costs 0 ms of TTS at runtime** (files/03 §4.5; §4.9.4 row 10), whatever
  the profile. The profile is paid once at build time.
- **The dynamic path** carries the whole self-hosted latency risk:
  - files/03 §4.5 budgets "TTS first byte … 140 ms dynamic" for row 11, a third-party
    measurement on an RTX 4090;
  - Freya has a 0.52 s floor (row 12);
  - these are recorded measurements, not product properties.
- An instruction adds prompt tokens, so measure time-to-first-audio per profile with
  `make tts-latency LIVE=1` (`scripts/voice/tts_latency.py`) and the turn with
  `make runtime-sim SCENARIO=<id> PROFILE=residency_tr`.
- **Rule:** a profile may not push the dynamic path's first byte past the §4.5 TTS term. If one
  does, that profile's instruction is dropped on the dynamic path only. It speaks `routine`
  there, and the cached path keeps the full profile. A slower voice is never traded for a warmer
  one mid-turn.
- `inference_timesteps` stays equal across tiers (§2). Lowering it on the dynamic path to buy
  latency would make the two tiers sound different.
- Record each measurement in `docs/evidence/<id>.md` with the date, the host, the model revision
  and the named corpus.

## 8. Listening-test protocol

The owner's listening review is owed for the ElevenLabs v1 table already, and it is required
before any self-hosted mapping ships.

1. **Corpus.** Use compiled catalogue sentences only: scripted `text_tr` from served or fixture
   packs. Never a patient answer and never patient audio. Take five sentences per context.
   Name the corpus by its list of `text_hash` values in the evidence file, so it can be replayed.
2. **Conditions per sentence:**
   - the profile under test;
   - `routine` as the neutral baseline;
   - for the self-hosted lane, the ElevenLabs rendering of the same profile as a reference.
3. **Blinding.** Randomise the order and hide the condition labels from the listener.
4. **Hard checks, pass or fail, for every clip.** Any failure blocks that profile:
   - the words are exactly `text_tr`, with nothing added, dropped or reordered, and no
     instruction read aloud;
   - no English leaking into Turkish;
   - no numeral heard as digits;
   - the same voice as the other contexts.
5. **Judged questions**, recorded as the listener's words and not as a score:
   - Does `welcome` sound warm without being theatrical?
   - Does `routine` sound professional?
   - Does `sensitive` sound gentle?
   - Do `red` and `instrument` sound steady and clear, never alarmed?
6. **Automated companion.** The per-profile round trip of §6 runs on the same corpus.
7. **Record** the date, the listeners' roles, the revisions, the profile versions and the
   outcome in `docs/evidence/<id>.md`, described as a measurement and never as a property of the
   product (invariant 20). A change to any value bumps that profile's `version`.

## 9. Cut-over checklist

- [ ] The listening review of the ElevenLabs v1 table is recorded (owner).
- [ ] `freya-tts` registry row completed: `model_id@revision`, `weights_sha256`,
      `licence_verified_at` from a raw LICENSE blob (§5).
- [ ] `voxcpm2-tts` controls re-checked against the pinned `voxcpm==2.0.3`: the instruction
      syntax, `cfg_value`, `inference_timesteps`, `seed`, `normalize`.
- [ ] `DeliveryProfile` gains the self-hosted block (§4 step 1). Every row's `version` is bumped
      and tests pin the new fields: validation, closed table, numeral-free instructions.
- [ ] The `/synthesize` body extended and the bridge updated. - The bridge must refuse digits in text and instruction and refuse unknown fields. - It must keep `normalize=False` and compose no instruction of its own. - Freya's response must be byte-identical with and without `delivery`. - The bridge change carries its own evidence.
- [ ] `HttpTtsGateway` sends the delivery block. The recorded-fixture and fake-transport tests
      prove the body, as `tests/voice/test_elevenlabs_clipgen.py` does for the cloud lane.
- [ ] `SpeechSynthesizer` (dynamic path) takes the profile, reviewed by `runtime-reviewer`. The
      Talker tool list is unchanged, and `make safety` is green.
- [ ] The per-profile round trip (§6) passes on the full compiled corpus for the self-hosted
      voice.
- [ ] Latency per profile measured (§7). Any profile over the §4.5 term runs `routine` on the
      dynamic path.
- [ ] Listening test (§8) passed for the self-hosted mapping. Any value changed bumps its
      version.
- [ ] `make clips VOICE=<self-hosted voice>` rebuilds with full coverage for every served pack.
      The RED clips are re-bundled into the app, since they are pre-positioned and never fetched.
- [ ] A new metric only if one is needed, and then catalogued in
      `observability/metrics_catalog.yaml` first (invariant 13). The existing
      `voice_clip_syntheses_total` already counts the build.

## 10. Options that need an ADR, not a profile edit

- **`eleven_v3` audio tags** (`[whispers]` and similar) could express warmth per phrase on the
  cloud lane.
  - v3 drops `speed`, `similarity_boost` and speaker boost.
  - Its tags would be text sent to the model, so they fall under the same closed-table and
    round-trip rules as the VoxCPM2 instruction.
  - Changing the pinned model needs an ADR, and the gateway refuses a profile tuned for another
    model.
- **A different self-hosted TTS** is a files/03 §4.9.1 row change, with its registry row and
  licence verification, before any profile is mapped to it.
