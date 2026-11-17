/**
 * Dev-lane voice (INT-194 → INT-559): the patient's words go to OUR
 * whisper-tr ASR on the team GPU box (through the dev Mac's port forward)
 * and the transcript lands in the intake's patient-note field.
 *
 * This is the demo bridge, not the product voice path: the product runtime
 * (INT-090s/135, INT-515) is LiveKit, which streams. Until INT-559 this lane
 * recorded a temporary file on the phone and deleted it after upload, and
 * CLAUDE.md invariant 3 allows no such dev exception. Now the microphone is
 * expo-audio's PCM stream into a bounded in-memory buffer (lib/capture) and
 * the ASR request carries bytes from memory (lib/capture/asrClient.ts): no
 * file path is ever created, and every buffer is zero by the time a turn
 * settles. The lane stays __DEV__-gated and synthetic-content only.
 *
 * Host probing is shared with the extract bridge (INT-199) via dev/hosts.ts:
 * Metro hostUri first (LAN mode names the dev Mac), then app.json
 * extra.asrHosts; first /health that answers wins.
 */
import { transcribeSegmentAt } from "./capture/asrClient";
import type { PcmSegment } from "./capture/types";
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

/**
 * One segment from memory to the ASR daemon. The segment is zero by the time
 * this settles, whichever way it went — there is no file to delete.
 */
export async function transcribeSegment(segment: PcmSegment): Promise<string> {
  const base = await reachableAsrBaseUrl();
  if (base === null) {
    segment.samples.fill(0);
    throw new Error("asr_unreachable");
  }
  return transcribeSegmentAt(base, segment);
}
