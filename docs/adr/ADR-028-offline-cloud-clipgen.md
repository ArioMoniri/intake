# ADR-028 · Offline cloud clip-gen for the fixed scripted set (amends ADR-021)

Status: Accepted (owner decision, INT-319)

## Context

ADR-021 and CLAUDE.md invariant 19 settled that every model runs self-hosted on
open weights, because the PHI path must not egress to a vendor. That reasoning
is about **patient** data on the **runtime** path. The scripted protocol
questions, red-flag scripts and validated instruments are a different asset:
they are committed to this repository in plain text, contain no patient answer,
and are spoken verbatim (invariant 10). The product owner asked for the best
available Turkish, expressive/emotional voice for exactly that fixed set, and
provided an ElevenLabs API key.

The self-hosted Turkish TTS (VoxCPM2, files/03 §4.9.1 rows 10-12) stays the
runtime lane for the small number of dynamic / `allow_paraphrase` lines, and it
is what INT-319's latency harness measures. What changes is only how the
**fixed** set gets its audio.

## Decision

A cloud TTS vendor (ElevenLabs) may be used for **offline clip generation only**:
`make clips` / the `voice_clips.gateway.ElevenLabsClipGenGateway` adapter
pre-synthesises the fixed set into the clip cache at build time, and at runtime
the device plays cached clips. The vendor is on no runtime and no PHI path.

Constraints, each enforced rather than promised:

- **Offline only, structurally.** The runtime speech adapter
  (`intake_voice_runtime.adapters.speech.refuse_external_host`) refuses every
  public host, so a session cannot reach a vendor even by misconfiguration. No
  runtime egress-allow-list row is added for cloud TTS, because the runtime
  never calls it. This is why the change does **not** weaken invariant 19: the
  PHI path is still all-self-hosted.
- **Key from the environment only.** `TTS_ELEVENLABS_API_KEY` (and an
  env-supplied base URL) — never a source file, a log, a trace or an exception
  message (files/10 §2). No vendor hostname is a literal anywhere in the tree,
  so `scripts/ci/assert_no_vendor_calls.sh` stays green.
- **Spend-gated.** The live paid call refuses without `EVAL_BUDGET_USD`, so a
  test and CI never dial it; recorded fixtures cover the tests (ADR-006).
- **Invariant 22 holds across the vendor too.** The compiler expands every
  numeral to Turkish orthography, `assert_speakable_tr` refuses a stray numeral
  before the wire, and the vendor's own normaliser is disabled
  (`apply_text_normalization: "off"`).
- **Invariant 10 holds.** The text sent is the verbatim `text_tr`; a recorded
  clip carrying edited text is refused.

## Consequences

The ElevenLabs vendor terms (commercial use of generated audio and voice
identity) and the KVKK Art. 9 question about sending scripted text to a US
vendor are **human blockers** — a vendor-contract and counsel decision, not an
agent's (docs/backlog/blockers.md; CLAUDE.md "When to stop and ask the human").
The live clip-gen and the production `make clips VOICE=<elevenlabs-...>` run
also wait on served packs (HB-C1: every pack is L0). A small, budget-capped live
validation (7 Turkish questions, 229 characters, docs/evidence/INT-319.md)
proved the mechanism end to end. The threat row is `cloud-clipgen`
(docs/security/threat-model.md). This ADR narrows ADR-021's scope — "self-hosted
on the runtime/PHI path" — rather than reversing it; re-adding a cloud vendor to
the **runtime** path remains a defect.

## Amendment — delivery profiles (INT-415, 27 Sep 2026)

This amendment changes no decision above. Each utterance now carries one of seven delivery
contexts. A server-side, versioned profile table (`voice_clips.delivery`) maps each context to
the `voice_settings` this lane sends, alongside the unchanged `model_id` and
`apply_text_normalization: "off"`.

- The text is still the verbatim, numeral-expanded `text_tr` (invariants 10 and 22).
- The model stays pinned, and a profile tuned for another model is refused before the wire.
- The clip object key gains the profile id and version: `clips/<locale>/<voice>/<profile>/<clip_id>`.
- RED clips are built under the most stable profile and remain pre-positioned. The dev
  on-demand route refuses them (invariant 21).

The mapping of the same profiles to the self-hosted `residency_tr` TTS is a guide,
`docs/voice/on-prem-tts-wiring.md`, and is not yet wired.
