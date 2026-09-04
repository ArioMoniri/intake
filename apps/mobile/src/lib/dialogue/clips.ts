/**
 * Expo-bound side of the dialogue clip cache (INT-233): the TTS host probe
 * (same dev-lane candidate walk as whisper/extract) and the filesystem the
 * pure ClipStore writes through.
 *
 * INT-243: that probe now walks a LADDER rather than one port — VoxCPM2 on
 * 8805 first (files/03 §4.9.1 rows 10-11), FreyaTTS on 8803 as the automatic
 * fallback (row 12). Order and ports come from app.json `extra.ttsLanes`,
 * not from a constant in this file; see ttsLane.ts.
 *
 * The clips under FileSystem.cacheDirectory/dialogue/ are AGENT-VOICE
 * audio: WAVs synthesized from catalog tr strings, one per question per
 * session. They are NOT patient audio — invariant 3 governs PATIENT
 * recordings, which keep the existing delete-after-upload posture in
 * lib/voice.ts (transcribeRecording deletes the file in its finally
 * block). The dialogue cache is still deleted wholesale on unmount AND on
 * session end: no session leaves audio behind, of either kind.
 */
import * as FileSystem from "expo-file-system/legacy";

import { configuredTtsLaneCandidates } from "../dev/expoHosts";
import { resolvePrebakedClip } from "./prebakedClipSource";
import { createClipStore, synthesizeClipWith, type ClipFs, type ClipStore } from "./tts";
import { createTtsLaneSelector, synthesizeWithFallback, type TtsLaneSelector } from "./ttsLane";

/**
 * The session's lane picker: probes the ladder once, keeps the answer, and
 * re-probes whenever a synthesis fails (INT-249). One of these per dialogue
 * session — it is the thing that owns "which model is this visit's voice".
 *
 * It replaces `reachableTtsLane` / `reachableTtsBaseUrl`, which resolved a
 * base on /health alone and returned it as a bare string. Both are deleted
 * rather than left as thin wrappers: a base is a decision taken once with no
 * way back, and keeping a function that hands one out is keeping the defect
 * within reach. Anything that needs a one-shot answer can call `selectTtsLane`
 * in ttsLane.ts, which measures.
 */
export function createDialogueTtsLaneSelector(): TtsLaneSelector {
  return createTtsLaneSelector(configuredTtsLaneCandidates);
}

export function dialogueClipDir(): string {
  return `${FileSystem.cacheDirectory}dialogue/`;
}

const expoClipFs: ClipFs = {
  async exists(path) {
    const info = await FileSystem.getInfoAsync(path);
    return info.exists;
  },
  async mkdirp(dir) {
    await FileSystem.makeDirectoryAsync(dir, { intermediates: true }).catch(() => undefined);
  },
  async writeBase64(path, base64) {
    await FileSystem.writeAsStringAsync(path, base64, {
      encoding: FileSystem.EncodingType.Base64,
    });
  },
  async removeDir(dir) {
    await FileSystem.deleteAsync(dir, { idempotent: true }).catch(() => undefined);
  },
};

/**
 * Session clip store bound to the lane SELECTOR and the app cache dir.
 *
 * INT-243 bound the store to one resolved base for the whole session, so a
 * lane that wedged after selection had no way back — every clip queued
 * behind it until the request cap fired and the dialogue failed. Binding to
 * the selector instead means each sentence asks "which lane can speak right
 * now", and a mid-session wedge degrades to the fallback voice.
 */
export function dialogueClipStore(selector: TtsLaneSelector): ClipStore {
  // INT-237 shaping is unchanged: one request per SENTENCE, trimmed, faded
  // and joined with a real sentence gap. INT-249 only changes where each of
  // those requests lands.
  //
  // INT-demo: the store first consults the bundled ElevenLabs clips
  // (`resolvePrebakedClip`). A prebaked hit plays offline in the demo voice
  // and never touches the live lane; a miss falls through to `synthesizeClipWith`
  // exactly as before, so the option-confirm turns and any un-baked string
  // still use the dev TTS ladder.
  return createClipStore(
    dialogueClipDir(),
    expoClipFs,
    (text) => synthesizeClipWith((sentence) => synthesizeWithFallback(selector, sentence), text),
    resolvePrebakedClip,
  );
}

/** Deletes every agent-voice clip of this session (unmount + session end). */
export async function clearDialogueClips(): Promise<void> {
  await expoClipFs.removeDir(dialogueClipDir());
}
