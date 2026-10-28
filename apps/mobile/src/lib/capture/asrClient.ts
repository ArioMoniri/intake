/**
 * The dev ASR client (INT-559): one segment from memory, as bytes, to
 * `/transcribe` on a base the caller has already found reachable. It never
 * sees a path. Whatever it was handed — the segment and the envelope built
 * from it — is zero by the time the promise settles, whichever way the
 * request went (invariant 3's posture, now with nothing left to delete).
 *
 * Every failure is a typed message the dialogue already understands
 * (`asr_unreachable` was the recorder path's; the rest name their cause).
 */
import { linearPcmEnvelope, pcmContentDescription } from "./envelope";
import type { PcmSegment } from "./types";

export const TRANSCRIBE_PATH = "/transcribe";

/**
 * A segment is at most sixty seconds of audio; a daemon that has not
 * answered one in ninety has hung, and a hung upload would otherwise hold
 * the turn's work id open for ever.
 */
export const SEGMENT_TIMEOUT_MS = 90_000;

export interface TranscribeOptions {
  fetchImpl?: typeof fetch;
  timeoutMs?: number;
  signal?: AbortSignal;
}

export async function transcribeSegmentAt(
  base: string,
  segment: PcmSegment,
  options: TranscribeOptions = {},
): Promise<string> {
  const { fetchImpl = fetch, timeoutMs = SEGMENT_TIMEOUT_MS, signal } = options;
  let envelope: Uint8Array<ArrayBuffer> | null = null;
  try {
    if (signal?.aborted) {
      throw new Error("asr_aborted");
    }
    envelope = linearPcmEnvelope(segment);
    const controller = new AbortController();
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, timeoutMs);
    const onAbort = () => controller.abort();
    signal?.addEventListener("abort", onAbort);
    let response: Response;
    try {
      response = await fetchImpl(`${base}${TRANSCRIBE_PATH}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/octet-stream",
          "X-Intake-Audio": pcmContentDescription(segment),
        },
        body: envelope,
        signal: controller.signal,
      });
    } catch {
      if (timedOut) {
        throw new Error("asr_timeout");
      }
      throw new Error(signal?.aborted ? "asr_aborted" : "asr_unreachable");
    } finally {
      clearTimeout(timer);
      signal?.removeEventListener("abort", onAbort);
    }
    if (!response.ok) {
      throw new Error("asr_unavailable");
    }
    let parsed: unknown;
    try {
      parsed = await response.json();
    } catch {
      throw new Error("asr_invalid_response");
    }
    const text =
      typeof parsed === "object" && parsed !== null && "text" in parsed
        ? (parsed as { text?: unknown }).text
        : undefined;
    return typeof text === "string" ? text.trim() : "";
  } finally {
    segment.samples.fill(0);
    envelope?.fill(0);
  }
}
