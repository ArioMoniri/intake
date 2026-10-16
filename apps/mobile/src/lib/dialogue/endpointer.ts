/**
 * End-of-turn detection for the spoken dialogue (INT-497).
 *
 * Until this, the patient's turn ended only when they tapped "Bitirdim". The
 * owner's order is "no delay": the agent should answer when the patient stops
 * talking, not when they find the button. files/03 §4.5 defines the turn gap
 * from the LAST PATIENT SPEECH SAMPLE, and a tap is not one — on the dev path
 * the gap the patient sat through was the speech end, plus however long they
 * took to tap, plus the pipeline.
 *
 * ## The rule
 *
 * A state machine over `(levelDbfs, atMs)` samples from the recorder's own
 * level meter — the same scalar barge-in reads (bargeIn.ts), never a buffer:
 *
 *   waiting  → speaking  once the level has stayed voiced for ONSET_MIN_MS;
 *   speaking → ended     once it has stayed unvoiced for the HANGOVER.
 *
 * "Voiced" is relative to the room: the floor is the quietest unvoiced level of
 * the last FLOOR_WINDOW_MS, and a voice must clear it by VOICED_MARGIN_DB —
 * clamped between VOICED_FLOOR_DBFS (a silent room never hears itself) and
 * VOICED_CEILING_DBFS (a noisy room never asks the patient to shout).
 *
 * ## The hangover, and why it is not one number
 *
 * files/03 §4.2's `min_silence_duration` (150/250 ms) is a VAD floor that sits
 * UNDER a trained turn detector; an energy rule on its own needs more, because
 * a hesitation inside an answer is also silence, and nothing in a level can
 * tell the two apart. Measured by replaying the cast voice's own level
 * envelopes through this module (scripts/voice/endpoint_replay.mjs,
 * docs/evidence/INT-497.md): one flat 450 ms wait cut 44 % of long or hesitant
 * utterances short; 850 ms cut 1.3 %. So the wait is chosen by the one
 * semantic signal the device has for free — what was asked, and what has been
 * said so far:
 *
 *   - a short answer to a question with an answer space ("evet", "dün akşam")
 *     rarely pauses inside itself — HANGOVER_SHORT_MS;
 *   - anything longer, and anything said to a free-text question, is a
 *     narrative with "…şey…" in it — HANGOVER_LONG_MS.
 *
 * And it learns, once per session, in the one direction that is safe: if the
 * patient talks over the next question within CUT_OFF_WINDOW_MS of an
 * automatic end, the end was premature, and every later turn waits one
 * HANGOVER_STEP_MS longer (up to HANGOVER_MAX_MS). It never shortens. "Neither
 * cuts off nor lags": it starts at the fast end and moves only on evidence.
 *
 * ## What it never does
 *
 * It never ends a turn nobody spoke in — silence alone is the tap's job, and
 * the long-silence path is untouched. Every failure of its INPUT is toward not
 * ending: a missing reading is skipped, a loud room raises the bar to the
 * ceiling and no higher, and the tap is always still there. What it can do is
 * end a turn during a pause longer than its wait — the measured trade, stated
 * in docs/evidence/INT-497.md. Nothing is lost when it does: the words already
 * said are transcribed and extracted against every open question (ask-ahead),
 * and speaking over the next question is a barge-in that reopens the floor and
 * widens the wait.
 *
 * Invariants 3 and 11: the input is a level the platform already computes;
 * nothing here reads, keeps or writes audio, and nothing here is an observer
 * lane — it is turn detection, which files/03 §4.2 puts on the critical path.
 */

/** How often the caller should feed a reading. Several per hangover, so the
 * hangover is a duration and not a coincidence of two samples. */
export const ENDPOINT_SAMPLE_MS = 50;

/** How long the level must stay voiced before it is speech, not a click. Under
 * the shortest one-word answer ("evet" ≈ 300 ms), over a cough's attack. */
export const ONSET_MIN_MS = 200;

/** How far above the room a voice has to be. Same order as barge-in's 9 dB
 * echo margin — there is no echo here (the agent is silent while listening),
 * so one more dB of margin costs nothing. */
export const VOICED_MARGIN_DB = 10;

/** Below this nothing is a voice, however quiet the room. */
export const VOICED_FLOOR_DBFS = -50;

/** Above this everything is a voice, however loud the room. Normal speech at
 * arm's length meters well above it; barge-in's absolute floor is -40. */
export const VOICED_CEILING_DBFS = -35;

/** Hysteresis: once speaking, a dip this far under the onset threshold is
 * still the voice — the gap between syllables is not the end of a sentence. */
export const RELEASE_DB = 4;

/** The room floor is the quietest unvoiced reading of this window. */
export const FLOOR_WINDOW_MS = 3000;

/** The floor assumed before any quiet reading arrives: it puts the threshold
 * at the ceiling, the conservative end, until the room has been heard. */
export const DEFAULT_FLOOR_DBFS = VOICED_CEILING_DBFS - VOICED_MARGIN_DB;

/** An answer shorter than this, from first to last voiced sample, is short. */
export const SHORT_ANSWER_MS = 1200;

/** The wait after a short answer. Replayed on short answers with a pause
 * inside them, 500 ms cut half of the 500 ms hesitations and 600 ms one in
 * twenty; with ~200 ms of pipeline after it, the turn gap of a short answer
 * still lands under the 800 ms p50 target (docs/evidence/INT-497.md). A pause
 * longer than this after a first word is cut ONCE — the session then widens. */
export const HANGOVER_SHORT_MS = 600;

/** The wait after a long or narrative answer: the knee of the measured
 * cut-off curve (1.3 % at 850 ms, 3.4 % at 800, 10.9 % at 700), and with the
 * pipeline still under the 1.2 s p95 target. */
export const HANGOVER_LONG_MS = 850;

/** How much longer every later turn waits after one premature end. */
export const HANGOVER_STEP_MS = 250;

/** The longest the detector ever waits. Past it the tap is the better tool. */
export const HANGOVER_MAX_MS = 1600;

/**
 * Speaking over the next question this soon after an AUTOMATIC end means the
 * end was premature. Covers the turn gap, barge-in's own deaf window and
 * calibration (bargeIn.ts ARM_DELAY_MS + CALIBRATION_MS) and its onset hold.
 */
export const CUT_OFF_WINDOW_MS = 2500;

/**
 * A tap on the speaking bubble this soon after an automatic end is the
 * "Bitirdim" tap the patient was already making — the turn had ended itself
 * under their finger. It is not an interruption of the question that started.
 */
export const LATE_TAP_GRACE_MS = 1200;

export type EndpointVerdict = "waiting" | "speaking" | "ended";

/**
 * What the question invites. A question with an answer space (options, a
 * yes/no) invites a short answer; a free-text question invites a narrative,
 * which gets the long wait from its first word.
 */
export type AnswerShape = "short" | "narrative";

/** The session's hangover: chosen per answer, widened per premature end. */
export interface HangoverPolicy {
  /** The wait after an answer voiced for `spokenMs`, to a question of `shape`. */
  hangoverMs(spokenMs: number, shape: AnswerShape): number;
  /** One automatic end turned out to be premature. */
  noteCutOff(): void;
}

export function createHangoverPolicy(): HangoverPolicy {
  let widened = 0;
  return {
    hangoverMs(spokenMs, shape) {
      const brief = shape === "short" && spokenMs < SHORT_ANSWER_MS;
      const base = brief ? HANGOVER_SHORT_MS : HANGOVER_LONG_MS;
      return Math.min(HANGOVER_MAX_MS, base + widened);
    },
    noteCutOff() {
      widened = Math.min(HANGOVER_MAX_MS, widened + HANGOVER_STEP_MS);
    },
  };
}

export interface Endpointer {
  /**
   * Feed one metering reading. `undefined` — what expo-audio returns until the
   * platform has a level — is SKIPPED: read as -160 dBFS it would end every
   * turn whose meter was late.
   */
  sample(levelDbfs: number | undefined, atMs: number): EndpointVerdict;
  /** When the voice was last heard: the real end of the patient's speech. */
  readonly lastVoicedAt: number | null;
  /** When the turn was declared over, or null. */
  readonly endedAt: number | null;
}

export interface EndpointerOptions {
  /** The patient was already speaking at this time — the listen began with a
   * barge-in — so the first words count and no onset is waited for. */
  readonly speakingAt?: number;
  /** What the question invites; a short answer when unsaid. */
  readonly shape?: AnswerShape;
}

function clamp(value: number, low: number, high: number): number {
  return Math.min(high, Math.max(low, value));
}

export function createEndpointer(
  policy: HangoverPolicy,
  options: EndpointerOptions = {},
): Endpointer {
  const shape: AnswerShape = options.shape ?? "short";
  let verdict: EndpointVerdict = options.speakingAt === undefined ? "waiting" : "speaking";
  let speechStartAt: number | null = options.speakingAt ?? null;
  let lastVoicedAt: number | null = options.speakingAt ?? null;
  let endedAt: number | null = null;
  let onsetAt: number | null = null;
  /** Unvoiced readings of the last FLOOR_WINDOW_MS: [atMs, levelDbfs]. */
  const quiet: [number, number][] = [];
  let floorDbfs = DEFAULT_FLOOR_DBFS;

  const thresholds = (): { on: number; off: number } => {
    const on = clamp(floorDbfs + VOICED_MARGIN_DB, VOICED_FLOOR_DBFS, VOICED_CEILING_DBFS);
    // Never let the release reach down into the room itself, and never above
    // the onset — a loud room has no hysteresis left to give.
    const off = Math.min(on, Math.max(on - RELEASE_DB, floorDbfs + RELEASE_DB));
    return { on, off };
  };

  const noteQuiet = (levelDbfs: number, atMs: number) => {
    quiet.push([atMs, levelDbfs]);
    while (quiet.length > 0 && atMs - quiet[0][0] > FLOOR_WINDOW_MS) {
      quiet.shift();
    }
    floorDbfs = Math.min(...quiet.map(([, level]) => level));
  };

  return {
    sample(levelDbfs, atMs) {
      if (verdict === "ended") {
        return verdict;
      }
      if (levelDbfs === undefined || !Number.isFinite(levelDbfs)) {
        return verdict;
      }
      const { on, off } = thresholds();
      if (verdict === "waiting") {
        if (levelDbfs < on) {
          onsetAt = null;
          noteQuiet(levelDbfs, atMs);
          return verdict;
        }
        onsetAt ??= atMs;
        if (atMs - onsetAt >= ONSET_MIN_MS) {
          verdict = "speaking";
          speechStartAt = onsetAt;
          lastVoicedAt = atMs;
        }
        return verdict;
      }
      // speaking
      if (levelDbfs >= off) {
        lastVoicedAt = atMs;
        return verdict;
      }
      noteQuiet(levelDbfs, atMs);
      const voicedFrom = speechStartAt ?? atMs;
      const heardUntil = lastVoicedAt ?? atMs;
      if (atMs - heardUntil >= policy.hangoverMs(heardUntil - voicedFrom, shape)) {
        verdict = "ended";
        endedAt = atMs;
      }
      return verdict;
    },
    get lastVoicedAt() {
      return verdict === "waiting" ? null : lastVoicedAt;
    },
    get endedAt() {
      return endedAt;
    },
  };
}

/** Did the patient talk over the next question because the turn ended early? */
export function isLikelyCutOff(autoEndedAt: number | null, voiceOnsetAt: number): boolean {
  return autoEndedAt !== null && voiceOnsetAt - autoEndedAt <= CUT_OFF_WINDOW_MS;
}

/** Is this tap the "Bitirdim" the patient was already reaching for? */
export function isLateFinishTap(autoEndedAt: number | null, tapAt: number): boolean {
  return autoEndedAt !== null && tapAt - autoEndedAt <= LATE_TAP_GRACE_MS;
}
