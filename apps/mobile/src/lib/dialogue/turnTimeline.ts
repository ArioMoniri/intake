/**
 * The turn timeline (INT-497): what the patient waited, measured where they
 * waited — on the device.
 *
 * `make runtime-sim` measures the server-side Talker on a virtual clock and
 * says so on every line; files/03 §4.5 defines the turn gap as "last patient
 * speech sample (VAD end) → first agent audio sample played on the device",
 * and only the device can see both ends of that. This module keeps the three
 * figures the owner's order names, for the session it lives in:
 *
 *   firstAudio  last voiced sample (endpointer.ts) → the first clip of the
 *               next turn actually playing;
 *   endpoint    last voiced sample → the turn taken (the hangover, as lived);
 *   join        dead air between two clips of one turn (track N's start minus
 *               the end of track N-1);
 *   asr         the recording handed to the ASR lane → its transcript back.
 *
 * Durations only. No text, no audio, no identifier beyond a running count, so
 * nothing here can carry what the patient said (invariants 3 and 6). A
 * measurement that was not taken is absent — a tapped turn with no voice
 * heard has no speech end, and gets no gap rather than a made-up one
 * (invariant 20's posture: a missing measurement is never zero).
 */

/** Readings kept per series. A long session must not grow without bound. */
export const TIMELINE_WINDOW = 200;

export type EndpointKind = "auto" | "tap";

export interface TurnTaken {
  readonly endpoint: EndpointKind;
  /** The endpointer's last voiced sample, or null when none was heard. */
  readonly speechEndAt: number | null;
  /** When the turn was taken (the endpoint fired, or the tap landed). */
  readonly at: number;
}

export interface TimelineSummary {
  readonly turns: number;
  readonly tappedTurns: number;
  readonly firstAudioP50Ms: number | null;
  readonly firstAudioP95Ms: number | null;
  readonly endpointP50Ms: number | null;
  readonly joinMaxMs: number | null;
  readonly joinP95Ms: number | null;
  readonly asrP50Ms: number | null;
  readonly asrP95Ms: number | null;
}

/** Nearest-rank percentile; null on no readings. */
export function percentile(values: readonly number[], p: number): number | null {
  if (values.length === 0) {
    return null;
  }
  const sorted = [...values].sort((a, b) => a - b);
  const rank = Math.max(1, Math.ceil((p / 100) * sorted.length));
  return sorted[Math.min(rank, sorted.length) - 1];
}

function push(series: number[], value: number): void {
  if (!Number.isFinite(value) || value < 0) {
    return; // not a slow turn: a broken clock
  }
  series.push(value);
  if (series.length > TIMELINE_WINDOW) {
    series.shift();
  }
}

export interface TurnTimeline {
  turnTaken(turn: TurnTaken): void;
  /** Audio started playing. Only the first start after a turn counts. */
  firstAudio(at: number): void;
  join(gapMs: number): void;
  asrSettled(ms: number): void;
  summary(): TimelineSummary;
}

export function createTurnTimeline(): TurnTimeline {
  const firstAudio: number[] = [];
  const endpoint: number[] = [];
  const joins: number[] = [];
  const asr: number[] = [];
  const kinds: EndpointKind[] = [];
  /** The turn waiting for its first audio, if any. */
  let open: TurnTaken | null = null;

  return {
    turnTaken(turn) {
      open = turn;
      kinds.push(turn.endpoint);
      if (kinds.length > TIMELINE_WINDOW) {
        kinds.shift();
      }
      if (turn.speechEndAt !== null) {
        push(endpoint, turn.at - turn.speechEndAt);
      }
    },
    firstAudio(at) {
      if (open === null) {
        return; // the opening, or a second clip of a turn already charged
      }
      if (open.speechEndAt !== null) {
        push(firstAudio, at - open.speechEndAt);
      }
      open = null;
    },
    join(gapMs) {
      push(joins, gapMs);
    },
    asrSettled(ms) {
      push(asr, ms);
    },
    summary() {
      return {
        turns: kinds.length,
        tappedTurns: kinds.filter((kind) => kind === "tap").length,
        firstAudioP50Ms: percentile(firstAudio, 50),
        firstAudioP95Ms: percentile(firstAudio, 95),
        endpointP50Ms: percentile(endpoint, 50),
        joinMaxMs: joins.length === 0 ? null : Math.max(...joins),
        joinP95Ms: percentile(joins, 95),
        asrP50Ms: percentile(asr, 50),
        asrP95Ms: percentile(asr, 95),
      };
    },
  };
}

export interface TrackStatus {
  /** Which track of the turn's queue is current. */
  readonly index: number;
  /** Position in that track, in seconds, as the player reports it. */
  readonly positionS: number;
  readonly durationS: number;
  readonly playing: boolean;
  /** When this status was seen, on the same clock as everything else. */
  readonly atMs: number;
}

export interface TrackObservation {
  /** This track's start, the first time it is seen playing. */
  readonly started?: number;
  /** Dead air before it, when the previous track's start was seen. */
  readonly join?: number;
}

/**
 * Track starts and joins, from the player's own status events.
 *
 * A status arrives late and on its own schedule, so it is not WHEN the audio
 * started. But it carries the position, and the start is (seen at) − (position):
 * exact however coarse the status interval is. The join is then the next
 * track's start minus (previous start + previous duration).
 */
export function createTrackClock(): {
  observe(status: TrackStatus): TrackObservation;
} {
  const starts = new Map<number, { at: number; durationMs: number }>();
  return {
    observe({ index, positionS, durationS, playing, atMs }) {
      if (!playing || !(positionS > 0) || starts.has(index)) {
        return {};
      }
      const started = atMs - positionS * 1000;
      starts.set(index, { at: started, durationMs: durationS * 1000 });
      const previous = starts.get(index - 1);
      if (previous === undefined || !Number.isFinite(previous.durationMs)) {
        return { started };
      }
      return { started, join: started - (previous.at + previous.durationMs) };
    },
  };
}
