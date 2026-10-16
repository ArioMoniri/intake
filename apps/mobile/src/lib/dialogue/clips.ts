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

import { buildApiBase } from "../auth/expoApiBase";
import { configuredTtsLaneCandidates } from "../dev/expoHosts";
import type { DeliveryContext } from "./deliveryContext";
import {
  fetchGeorgeClip,
  georgePreferringSynth,
  type GeorgeGenerator,
  type ScriptedTr,
} from "./georgeClip";
import { createClipStore, synthesizeClipWith, type ClipFs, type ClipStore } from "./tts";
import { createTtsLaneSelector, synthesizeWithFallback, type TtsLaneSelector } from "./ttsLane";

/** The dev API host the George clip route lives on: the same resolver, and so
 * the same LAN walk, as the auth/records clients (INT-328). Null when no dev
 * host answers. */
function firstReachableApiBase(): Promise<string | null> {
  return buildApiBase().catch(() => null);
}

/**
 * The DEV-ONLY George clip source (ADR-028 on-demand variant), or null.
 *
 * `null` in production — invariant 19 stays intact, the PHI path is
 * self-hosted, and the store uses only the self-hosted lane exactly as before.
 * `null` too when no dev API host answers, so a demo with the API down still
 * speaks in the self-hosted voice. When present it POSTs SCRIPTED question text
 * to the dev server route; the DEVICE never holds the vendor key (the server
 * reads it from its env), and a `ScriptedTr` is the only thing it can be handed.
 */
function createGeorgeSource(): GeorgeGenerator | null {
  if (!__DEV__) {
    return null;
  }
  let baseP: Promise<string | null> | null = null;
  const resolveBase = (): Promise<string | null> => {
    if (baseP === null) {
      baseP = firstReachableApiBase();
    }
    return baseP;
  };
  return async (text: ScriptedTr, context?: DeliveryContext): Promise<Uint8Array> => {
    const base = await resolveBase();
    if (base === null) {
      baseP = null; // a later turn re-probes rather than staying muted
      throw new Error("george_unavailable");
    }
    try {
      // INT-415: the utterance's delivery context rides along; the server maps
      // it to its own profile (the device holds no voice setting)
      return await fetchGeorgeClip(base, text, { context });
    } catch (error) {
      baseP = null; // degrade this turn to the self-hosted lane, re-probe next
      throw error;
    }
  };
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
export function dialogueClipStore(selector: TtsLaneSelector): ClipStore {
  // INT-237 shaping is unchanged: one request per SENTENCE, trimmed, faded
  // and joined with a real sentence gap. INT-249 only changes where each of
  // those requests lands.
  const selfHosted = (text: string): Promise<Uint8Array> =>
    synthesizeClipWith((sentence) => synthesizeWithFallback(selector, sentence), text);
  // ADR-028 (on-demand variant): in dev, prefer George's cloud voice for a
  // scripted question with no cached clip, and degrade to the self-hosted lane
  // on any failure. Null in prod, so this is the SAME store as before there.
  const george = createGeorgeSource();
  if (george === null) {
    return createClipStore(dialogueClipDir(), expoClipFs, selfHosted);
  }
  const prefer = georgePreferringSynth(george, selfHosted);
  // The store is only ever fed catalog-composed SCRIPTED text
  // (useDialogueSession → speech.ts questionSpeechTr/confirmSpeechTr); patient
  // words are DISPLAYED, never synthesized (invariant 2/10). This is the single
  // point where that architectural fact is asserted as a ScriptedTr — every
  // OTHER path to the George vendor requires a ScriptedTr minted from an
  // IntakeQuestion (georgeClip.ts), so patient words cannot reach the vendor.
  //
  // INT-414: the store also hands on each clip's delivery context, which
  // `prefer` forwards to George (INT-415) and the self-hosted lane ignores.
  // Delivery lines reach the store the same way questions do: minted from a
  // deck key (`scriptedDeliveryTr`), never from anything the patient said.
  return createClipStore(dialogueClipDir(), expoClipFs, (text, context) =>
    prefer(text as ScriptedTr, context),
  );
}

/** Deletes every agent-voice clip of this session (unmount + session end). */
export async function clearDialogueClips(): Promise<void> {
  await expoClipFs.removeDir(dialogueClipDir());
}
