/**
 * Expo-bound side of the dialogue clip cache (INT-233): the TTS host probe
 * (same dev-lane candidate walk as whisper/extract) and the filesystem the
 * pure ClipStore writes through.
 *
 * INT-240: that probe now walks a LADDER rather than one port — VoxCPM2 on
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
import { createClipStore, synthesizeWav, type ClipFs, type ClipStore } from "./tts";
import { resolveTtsLane, type TtsLaneBase } from "./ttsLane";

/**
 * First lane in the ladder whose /health answers — VoxCPM2 (8805) before
 * Freya (8803); null when the whole ladder is down.
 */
export async function reachableTtsLane(): Promise<TtsLaneBase | null> {
  return resolveTtsLane(configuredTtsLaneCandidates());
}

/** First TTS base whose /health answers; null when the lane is down. */
export async function reachableTtsBaseUrl(): Promise<string | null> {
  return (await reachableTtsLane())?.base ?? null;
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
  return createClipStore(dialogueClipDir(), expoClipFs, (text) => synthesizeWav(base, text));
}

/** Deletes every agent-voice clip of this session (unmount + session end). */
export async function clearDialogueClips(): Promise<void> {
  await expoClipFs.removeDir(dialogueClipDir());
}
