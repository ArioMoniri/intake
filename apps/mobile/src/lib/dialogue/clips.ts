/**
 * Expo-bound side of the dialogue clip cache (INT-233): the FreyaTTS host
 * probe (same dev-lane candidate walk as whisper/extract) and the
 * filesystem the pure ClipStore writes through.
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

import { configuredServiceCandidates } from "../dev/expoHosts";
import { reachableBaseUrl } from "../dev/hosts";
import { createClipStore, synthesizeClip, TTS_PORT, type ClipFs, type ClipStore } from "./tts";

/** First TTS base whose /health answers; null when the lane is down. */
export async function reachableTtsBaseUrl(): Promise<string | null> {
  return reachableBaseUrl(configuredServiceCandidates(TTS_PORT));
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

/** Session clip store bound to the probed base and the app cache dir. */
export function dialogueClipStore(base: string): ClipStore {
  // INT-237: synthesizeClip, not synthesizeWav — one request per sentence,
  // trimmed, faded and joined with a real sentence gap.
  return createClipStore(dialogueClipDir(), expoClipFs, (text) => synthesizeClip(base, text));
}

/** Deletes every agent-voice clip of this session (unmount + session end). */
export async function clearDialogueClips(): Promise<void> {
  await expoClipFs.removeDir(dialogueClipDir());
}
