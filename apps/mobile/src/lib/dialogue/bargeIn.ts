/**
 * Speech-onset detection for barge-in (INT-291).
 *
 * The defect this exists for: while the agent spoke, the dev-tier dialogue
 * set `allowsRecording: false` and started no recorder, so there was no
 * microphone at all. Speaking over the agent did *nothing*. The only two
 * interrupts were a tap on the speaking bubble and a typed message, and
 * neither is something a patient in pain reliably reaches for. files/02 §8.2
 * budgets a barge-in stop at 150 ms; before this there was no barge-in to
 * budget unless a finger was involved.
 *
 * ## Why a pure function
 *
 * The decision has to be provable without a microphone. The one simulator
 * available to this repo records silence, so an energy rule wired straight
 * into the hook would be untestable in exactly the way that matters. So the
 * rule lives here as a state machine over `(levelDbfs, atMs)` samples, and
 * the hook only supplies the samples.
 *
 * ## The self-echo problem, and how the threshold is set
 *
 * `files/00_STATE.md` §2 records the AEC/AGC collision: with the mic open on
 * speakerphone, the agent's own speech is captured. A fixed threshold would
 * therefore make the agent cut itself off mid-question — the worst possible
 * answer to "the voice is robotic". There is no API at this tier that can
 * tell the agent's echo from the patient, so the threshold is **measured per
 * clip** instead of assumed:
 *
 *   1. `ARM_DELAY_MS` — deaf while the clip's opening word plays. The
 *      patient's answer to the *previous* turn is often still in the air; a
 *      detector armed at sample zero would eat the first word of every
 *      question and the patient would never hear what they were asked.
 *   2. `CALIBRATION_MS` — the loudest level seen in this window is taken as
 *      this room's echo-plus-noise floor, for this clip, at this volume, on
 *      this speaker.
 *   3. Fire only above `floor + ECHO_MARGIN_DB`, and never below
 *      `MIN_TRIGGER_DBFS`, held for `ONSET_HOLD_MS`.
 *
 * Every failure mode of that ladder is toward **not** interrupting: a poisoned
 * calibration (the patient talks during the window) raises the threshold and
 * the clip simply stays tap-interruptible, which is exactly where the product
 * was before this module. It never fails toward cutting the agent off.
 *
 * ## Invariant 3
 *
 * Nothing here touches audio. The input is a scalar the platform already
 * computes for its own level meter; no buffer is read, retained or written,
 * and there is no path from this module to the filesystem.
 */

/**
 * Deaf window at the start of a clip.
 *
 * Sized to cover the agent's opening word: the shortest catalog turn measured
 * on the Freya lane ran 1.00–1.24 s (docs/evidence/INT-291.md), so ~a third of
 * the shortest turn is the first word plus its onset.
 */
export const ARM_DELAY_MS = 400;

/** Window whose loudest sample is taken as this clip's echo-and-noise floor. */
export const CALIBRATION_MS = 400;

/**
 * How far above the measured floor the patient has to be.
 *
 * 9 dB is ~2.8× in amplitude. Below ~6 dB the margin is inside the level
 * variation of the agent's own speech across a sentence; far above it, only a
 * shout interrupts.
 */
export const ECHO_MARGIN_DB = 9;

/**
 * Absolute floor, whatever the room measured.
 *
 * A silent room calibrates very low, and without this the threshold would
 * land under the noise of a fan and every turn would be cut by nothing.
 */
export const MIN_TRIGGER_DBFS = -40;

/**
 * How long the level must stay up before it counts as a turn.
 *
 * Above the agent's own inter-sentence pause (`SENTENCE_GAP_MS`, 200 ms) so a
 * reflex "hı-hı" landing in that gap is not read as the patient taking the
 * floor, and short enough that a real interruption still stops the agent
 * inside the files/02 §8.2 budget once the stop itself is charged.
 */
export const ONSET_HOLD_MS = 240;

/**
 * How often the caller should feed a reading.
 *
 * Several samples inside `ONSET_HOLD_MS`, so the hold is a real duration and
 * not a two-sample coincidence, and cheap enough to run for the whole clip:
 * one scalar read per tick, no allocation.
 */
export const BARGE_IN_SAMPLE_MS = 50;

/** What the detector is doing right now. Reported rather than a bare boolean
 * so the caller can tell "not yet armed" from "armed and hearing nothing". */
export type OnsetVerdict = "warming" | "calibrating" | "listening" | "fired";

export interface SpeechOnsetDetector {
  /**
   * Feed one metering reading. `undefined` — which expo-audio returns until
   * the platform has produced a level — is SKIPPED, not read as silence:
   * treating it as −160 dBFS would drag the calibrated floor down and arm a
   * hair trigger on the next clip.
   */
  sample(levelDbfs: number | undefined, atMs: number): OnsetVerdict;
}

export function createSpeechOnsetDetector(): SpeechOnsetDetector {
  let startedAt: number | null = null;
  let floorDbfs = Number.NEGATIVE_INFINITY;
  let onsetStartedAt: number | null = null;
  let fired = false;

  return {
    sample(levelDbfs, atMs) {
      if (fired) {
        return "fired";
      }
      if (levelDbfs === undefined || !Number.isFinite(levelDbfs)) {
        return verdictFor(startedAt, atMs);
      }
      startedAt ??= atMs;
      const elapsed = atMs - startedAt;
      if (elapsed < ARM_DELAY_MS) {
        return "warming";
      }
      if (elapsed < ARM_DELAY_MS + CALIBRATION_MS) {
        floorDbfs = Math.max(floorDbfs, levelDbfs);
        return "calibrating";
      }
      const threshold = Math.max(floorDbfs + ECHO_MARGIN_DB, MIN_TRIGGER_DBFS);
      if (levelDbfs <= threshold) {
        onsetStartedAt = null;
        return "listening";
      }
      onsetStartedAt ??= atMs;
      if (atMs - onsetStartedAt >= ONSET_HOLD_MS) {
        fired = true;
        return "fired";
      }
      return "listening";
    },
  };

  function verdictFor(begun: number | null, atMs: number): OnsetVerdict {
    if (begun === null) {
      return "warming";
    }
    const elapsed = atMs - begun;
    if (elapsed < ARM_DELAY_MS) {
      return "warming";
    }
    return elapsed < ARM_DELAY_MS + CALIBRATION_MS ? "calibrating" : "listening";
  }
}
