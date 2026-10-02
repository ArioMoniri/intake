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

import { AuthApiError, authedFetch } from "../auth/api";
import { getAccessToken, getRefreshToken } from "../auth/tokens";
import { configuredTtsLaneCandidates } from "../dev/expoHosts";
import type { DeliveryContext } from "./deliveryContext";
import {
  fetchGeorgeClipVia,
  georgePreferringSynth,
  GeorgeUnavailable,
  type ClipLaneRecord,
  type GeorgeGenerator,
  type GeorgeTransport,
  type ScriptedTr,
} from "./georgeClip";
import { createClipStore, synthesizeClipWith, type ClipFs, type ClipStore } from "./tts";
import { createTtsLaneSelector, synthesizeWithFallback, type TtsLaneSelector } from "./ttsLane";

/**
 * The George request's transport: the DPoP-bound `authedFetch` the records and
 * consent clients use, which resolves the API base (INT-328, and its INT-440
 * hosted fallback) and signs the request as the signed-in patient.
 *
 * INT-326 put the route behind `require_patient`; the client kept posting
 * anonymously and every request became a 401 the fallback swallowed (INT-440).
 * A device with no patient session — a dev test account, or nobody signed in
 * — has nothing to sign with, and that is reported as such rather than sent.
 */
const authedGeorgeTransport: GeorgeTransport = async (path, init) => {
  // No session to sign with: say so before any host walk, so a clip the
  // George route could never serve costs the turn nothing on its way to the
  // self-hosted lane.
  if (getAccessToken() === null && (await getRefreshToken()) === null) {
    throw new GeorgeUnavailable("no_session");
  }
  try {
    return await authedFetch(path, init);
  } catch (error) {
    if (error instanceof AuthApiError) {
      throw new GeorgeUnavailable(error.kind === "session" ? "no_session" : "no_host");
    }
    throw error;
  }
};

/**
 * The DEV-ONLY George clip source (ADR-028 on-demand variant), or null.
 *
 * `null` in production — invariant 19 stays intact, the PHI path is
 * self-hosted, and the store uses only the self-hosted lane exactly as before.
 * When present it POSTs SCRIPTED question text to the dev server route as the
 * signed-in patient; the DEVICE never holds the vendor key (the server reads
 * it from its env), and a `ScriptedTr` is the only thing it can be handed.
 */
function createGeorgeSource(): GeorgeGenerator | null {
  if (!__DEV__) {
    return null;
  }
  // INT-415: the utterance's delivery context rides along; the server maps it
  // to its own profile (the device holds no voice setting)
  return (text: ScriptedTr, context?: DeliveryContext): Promise<Uint8Array> =>
    fetchGeorgeClipVia(authedGeorgeTransport, text, { context });
}

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
export function dialogueClipStore(
  selector: TtsLaneSelector,
  onClipLane?: (text: string, record: ClipLaneRecord) => void,
): ClipStore {
  // ADR-028 (on-demand variant): in dev, prefer George's cloud voice for a
  // scripted question with no cached clip, and degrade to the self-hosted lane
  // on any failure. Null in prod, where `georgePreferringSynth` goes straight
  // to the self-hosted lane and reports it as `off`.
  const george = createGeorgeSource();
  // The store is only ever fed catalog-composed SCRIPTED text
  // (useDialogueSession → speech.ts questionSpeechTr/confirmSpeechTr); patient
  // words are DISPLAYED, never synthesized (invariant 2/10). This is the single
  // point where that architectural fact is asserted as a ScriptedTr — every
  // OTHER path to the George vendor requires a ScriptedTr minted from an
  // IntakeQuestion (georgeClip.ts), so patient words cannot reach the vendor.
  return createClipStore(dialogueClipDir(), expoClipFs, (text) => {
    // INT-440: one utterance per clip on the self-hosted lane (INT-249 picks
    // where it lands), and every clip reports the lane — and tier — that spoke.
    const tiers: string[] = [];
    const selfHosted = (scripted: string): Promise<Uint8Array> =>
      synthesizeClipWith(
        (utterance) =>
          synthesizeWithFallback(selector, utterance, {}, (lane) => {
            if (!tiers.includes(lane.id)) {
              tiers.push(lane.id);
            }
          }),
        scripted,
      );
    const prefer = georgePreferringSynth(george, selfHosted, (outcome) => {
      onClipLane?.(text, outcome.lane === "self_hosted" ? { ...outcome, tiers } : outcome);
    });
    return prefer(text as ScriptedTr);
  });
}

/** Deletes every agent-voice clip of this session (unmount + session end). */
export async function clearDialogueClips(): Promise<void> {
  await expoClipFs.removeDir(dialogueClipDir());
}
