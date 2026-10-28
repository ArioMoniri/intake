/**
 * One turn of the microphone (INT-559), as the dialogue and the voice-note
 * pill both run it: open the stream, hand every cap-sized segment to the ASR
 * client the moment the session hands it out, and settle the transcript at
 * finish from the segments in order.
 *
 * The stream factory and the ASR client are ports: useDialogueSession.ts and
 * VoiceNote.tsx hand in the expo-audio binding (expoStream.ts) and the dev
 * ASR client (lib/voice.ts); turn.test.ts hands in fakes. `closed` is the
 * INT-551 pattern — read before the lazy native import, after it, and by the
 * session on every chunk — so a RED that lands anywhere in the opening leaves
 * no microphone behind it (invariants 9 and 21).
 *
 * The turn's own `discard` and `finish` end it the same way (the review of
 * #964): either can land while `open` is suspended in the native import or
 * the stream's start, so both set a flag that `open` reads after every await
 * and that the session reads as part of its `closed`. A stream the import
 * created for an ended turn is released without ever being started.
 */
import { createCaptureSession, type CaptureSession } from "./session";
import { CAPTURE_FORMAT, type PcmFormat, type PcmSegment, type PcmStreamPort } from "./types";

export interface CaptureTurnDeps {
  createStream: (format: PcmFormat) => Promise<PcmStreamPort>;
  transcribe: (segment: PcmSegment) => Promise<string>;
  closed: () => boolean;
  format?: PcmFormat;
  maxSeconds?: number;
}

export interface CaptureTurn {
  /**
   * Open the microphone unless the dialogue closes, or the turn is discarded
   * or finished, first; whether it is capturing.
   */
  open(): Promise<boolean>;
  readonly capturing: boolean;
  /** True once any sample arrived in this turn; survives finish and discard. */
  readonly heard: boolean;
  /** The level of the chunk that arrived last (for the barge-in watch). */
  levelDbfs(): number | undefined;
  /** True when no sample is held. */
  zeroed(): boolean;
  /**
   * Close the microphone and settle the whole turn's transcript. Null when
   * the turn heard nothing. Rejects when a segment could not be transcribed —
   * the microphone is closed and zeroed by then either way.
   */
  finish(): Promise<string | null>;
  /** Close the microphone and zero; nothing is sent, nothing settles. Ends an open in flight. */
  discard(): void;
}

/** The segment texts in order, empties dropped. */
export function joinTranscripts(parts: readonly string[]): string {
  return parts
    .map((part) => part.trim())
    .filter((part) => part.length > 0)
    .join(" ");
}

export function createCaptureTurn(deps: CaptureTurnDeps): CaptureTurn {
  const { createStream, transcribe } = deps;
  let session: CaptureSession | null = null;
  let uploads: Promise<string>[] = [];
  /** Set by `discard`: an open suspended at an await leaves nothing behind it. */
  let discarded = false;
  /** Set by `finish`: the turn is over, so an open still in flight never starts capturing. */
  let finished = false;
  const closed = () => discarded || finished || deps.closed();

  const send = (segment: PcmSegment) => {
    const upload = transcribe(segment);
    // Marked handled here so a cap segment that fails before `finish` is
    // awaited does not surface as an unhandled rejection; `finish` still
    // sees the rejection through Promise.all.
    upload.catch(() => undefined);
    uploads.push(upload);
  };

  return {
    async open() {
      if (session?.capturing) {
        return true;
      }
      if (closed()) {
        return false;
      }
      const stream = await createStream(deps.format ?? CAPTURE_FORMAT);
      if (closed()) {
        // Never started; the native object the import created is released.
        stream.stop();
        return false;
      }
      session = createCaptureSession({
        stream,
        closed,
        onSegment: send,
        maxSeconds: deps.maxSeconds,
      });
      return session.open();
    },
    get capturing() {
      return session?.capturing === true;
    },
    get heard() {
      return (session?.samplesHeard() ?? 0) > 0;
    },
    levelDbfs: () => session?.levelDbfs(),
    zeroed: () => session === null || session.zeroed(),
    async finish() {
      finished = true;
      const tail = session?.finish() ?? null;
      if (tail !== null) {
        send(tail);
      }
      const pending = uploads;
      uploads = [];
      if (pending.length === 0) {
        return null;
      }
      return joinTranscripts(await Promise.all(pending));
    },
    discard() {
      discarded = true;
      session?.discard();
      uploads = [];
    },
  };
}
