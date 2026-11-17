/**
 * The device half of CD-24 `generic_red_unknown_no_answer_goes_remote` (INT-465).
 *
 * Under UNKNOWN a RED asks one question first, with no 112 control, because
 * showing 112 before the answer would guess that the patient is at home
 * (files/02 §5.3; files/04 §8.1 rule 7). A patient who cannot answer must still
 * get an action. When the question stays unanswered for
 * `UNSIGNED_LOCATION_NO_ANSWER_WAIT_MS`, the store takes the rule's own
 * `on_no_answer` branch, which is REMOTE with the 112 control in every
 * committed rule. Never silence.
 *
 * The wait is an UNSIGNED engineering value: CD-24 keeps `no_answer_wait`
 * draft_needs_source (see store.ts).
 *
 * A time limit under WCAG 2.2 SC 2.2.1. e2e/a11y.spec.ts registers it as the one
 * Essential-Exception time limit, with its reason.
 *
 * A module of its own, so a fake clock can drive it and no component owns a
 * timer (BK13).
 */
import { UNSIGNED_LOCATION_NO_ANSWER_WAIT_MS, type RedStore } from "./store";

export interface NoAnswerTimers {
  readonly set: (run: () => void, ms: number) => unknown;
  readonly clear: (handle: unknown) => void;
}

const REAL_TIMERS: NoAnswerTimers = {
  set: (run, ms) => setTimeout(run, ms),
  clear: (handle) => clearTimeout(handle as ReturnType<typeof setTimeout>),
};

/** Start the wait on an asked location question. Returns the cancel. */
export function startNoAnswerClock(
  store: Pick<RedStore, "answerLocation">,
  timers: NoAnswerTimers = REAL_TIMERS,
): () => void {
  const handle = timers.set(
    () => store.answerLocation("noAnswer"),
    UNSIGNED_LOCATION_NO_ANSWER_WAIT_MS,
  );
  return () => timers.clear(handle);
}
