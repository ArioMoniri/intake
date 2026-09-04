/**
 * The one content hash the prebaked-clip path keys on (INT-demo ElevenLabs
 * lane). A clip is bound to the EXACT `text_tr` it was synthesised from —
 * change a word and the hash changes, so a stale clip can never play under a
 * question whose wording moved (CLAUDE.md invariant 10, verbatim). This is the
 * dev-mobile mirror of `protocols.dsl.clip_text_hash`: the compiled runtime
 * keys its MinIO cache on sha256(text_tr,voice_id), and this keys the bundled
 * dev cache on sha256(text_tr) — the voice is a single build-time constant
 * here (one bundled voice per build), so it is not folded into the key.
 *
 * Deliberately `@noble/hashes` and not `expo-crypto`: this exact function runs
 * in BOTH worlds — Hermes at runtime (the resolver) and Node under vitest (the
 * enumerator that emits the manifest the generator reads) — so the hash a
 * clip's filename is minted from and the hash the app looks it up by come from
 * one pure implementation and cannot drift. `expo-crypto` is a native module
 * and is async; neither fits the enumerator.
 */
import { sha256 } from "@noble/hashes/sha2.js";
import { bytesToHex, utf8ToBytes } from "@noble/hashes/utils.js";

/** Lower-case hex sha256 of the verbatim spoken text. */
export function clipTextHash(text: string): string {
  return bytesToHex(sha256(utf8ToBytes(text)));
}
