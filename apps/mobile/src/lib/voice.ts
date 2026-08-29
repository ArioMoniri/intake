/**
 * Dev-lane voice note (INT-194): recorded audio goes to OUR whisper-tr
 * ASR on the team GPU box (through the dev Mac's port forward) and the
 * transcript lands in the intake's patient-note field.
 *
 * This is the demo bridge, not the product voice path: the product runtime
 * (INT-090s/135) is LiveKit with mlocked ≤60 s buffers and never writes
 * audio to disk (invariant 3). This lane is __DEV__-gated, synthetic
 * content only, and the recording file is deleted right after upload.
 *
 * Host probing is shared with the extract bridge (INT-199) via dev/hosts.ts:
 * Metro hostUri first (LAN mode names the dev Mac), then app.json
 * extra.asrHosts; first /health that answers wins.
 */
import * as FileSystem from "expo-file-system/legacy";

import { configuredServiceCandidates } from "./dev/expoHosts";
import { probeReachability, serviceCandidates, type ReachabilityReport } from "./dev/hosts";

export const ASR_PORT = 8802;

/** Candidate ASR bases, most specific first (kept for INT-194 callers). */
export function asrCandidates(hostUri: string | undefined, extraHosts: string[]): string[] {
  return serviceCandidates(hostUri, extraHosts, ASR_PORT);
}

/**
 * The ASR walk with its detail intact (INT-246): which bases were tried and
 * how each one failed. One probe pass, same as before — this is the same
 * walk `reachableAsrBaseUrl` takes, reported instead of discarded.
 */
export async function probeAsrReachability(): Promise<ReachabilityReport> {
  return probeReachability(configuredServiceCandidates(ASR_PORT));
}

/** Unchanged signature for every existing caller: a base, or null. */
export async function reachableAsrBaseUrl(): Promise<string | null> {
  return (await probeAsrReachability()).base;
}

/** Invariant-3 posture even in the dev lane: no audio lingers on disk. */
export async function discardRecording(uri: string): Promise<void> {
  await FileSystem.deleteAsync(uri, { idempotent: true }).catch(() => undefined);
}

export async function transcribeRecording(uri: string): Promise<string> {
  const base = await reachableAsrBaseUrl();
  if (base === null) {
    await discardRecording(uri);
    throw new Error("asr_unreachable");
  }
  try {
    const result = await FileSystem.uploadAsync(`${base}/transcribe`, uri, {
      httpMethod: "POST",
      headers: { "Content-Type": "application/octet-stream" },
      uploadType: FileSystem.FileSystemUploadType.BINARY_CONTENT,
    });
    const parsed: { text?: string } = JSON.parse(result.body);
    return (parsed.text ?? "").trim();
  } finally {
    await discardRecording(uri);
  }
}
