/**
 * The single, swappable config for the demo's prebaked ElevenLabs voice
 * (ADR-028 offline clip-gen, applied to the dev-mobile demo lane).
 *
 * Changing the voice is changing THESE two constants and re-running the
 * generator — the id is never spread across the generator, the manifest and the
 * runtime. The manifest the generator consumes carries the voice/model as data
 * copied from here, so the bundled clips and this constant cannot disagree
 * about which voice was synthesised.
 *
 * `eleven_multilingual_v2` has Turkish among its languages; the generator sends
 * `apply_text_normalization: "off"` (the vendor normaliser is disabled, so the
 * compiler/`assertSpeakableTr` numeral expansion is the only one that runs —
 * CLAUDE.md invariant 22). No accuracy or quality claim is made here or
 * anywhere in the tree (invariant 20); this is configuration.
 */

/** ElevenLabs voice id — "George" (a warm Turkish-capable multilingual voice). */
export const DEMO_CLIP_VOICE_ID = "JBFqnCBsd6RMkjVDRZzb";

/** ElevenLabs model id used for the offline synthesis. */
export const DEMO_CLIP_MODEL_ID = "eleven_multilingual_v2";
