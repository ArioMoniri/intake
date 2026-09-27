/**
 * The RED motion contract (INT-333, MOTION-4; ADR-033 §5, Proposed;
 * docs/design/motion/motion-verification.md §1.1 U1–U5, §3 S-1, S-5, S-6,
 * §4 MOTION-4; files/02 §5.3; CLAUDE.md invariant 21).
 *
 * Pure — no React Native, Reanimated, router or haptics import — so every
 * register × location × reduce-motion combination is node-testable, and the
 * RED UI (INT-135) spreads an answer from here instead of writing its own.
 *
 * Four decisions, each fail-closed while ADR-033's open questions stand:
 *
 * - **Zero motion.** A RED enters in 0 ms with 0 ms delay and leaves in 0 ms.
 *   Nothing on it loops, flashes or staggers; it never dismisses itself on a
 *   timer and never by a gesture. The answer is the same at every
 *   reduce-motion setting, because there is no movement for reduce-motion to
 *   remove. Its actions commit on press, with instant feedback and no
 *   long-press.
 * - **First paint is a root layer, never behind a navigator.** ALERT and CALM
 *   paint as a layer mounted beside the navigator container and fed by the
 *   RED event itself. They are never a native-stack push: react-native-screens
 *   defers a push requested during an in-flight transition until that
 *   transition ends (S-1). They are never an RN `Modal` either, which is a
 *   UIKit presentation: animated, and held by the same transition. SILENT
 *   renders in the flow of the session. DEFERRED_CLINICIAN is invisible to the
 *   motion layer: it changes nothing on the patient's screen (files/02 §5.3,
 *   "Patient screen unchanged"), so motion cannot become a side channel for a
 *   finding meant for the clinician alone (S-6).
 * - **No 112 mounts before the location allows it.** Under ON_SITE the 112
 *   control is absent, not de-emphasised, and never mounted even for one
 *   frame (invariant 21). Under UNKNOWN it is not rendered until the one
 *   location question is answered (files/02 §5.3, action table; ADR-033 Q4's
 *   fail-closed default), so an answer of "in hospital" can never remove a 112
 *   control the patient already saw. The pack's authorisation
 *   (`RedPresentation.show112`, already clamped for ON_SITE by `resolveRed`)
 *   can narrow this and never widen it.
 * - **No haptic, for any register** (ADR-033 Q2's fail-closed default).
 *
 * The yields say what the rest of the screen does when a RED is presented.
 * They are keyed on `redPresentationMode(register) !== "none"`, never on "a
 * RED event arrived" (S-6), so a DEFERRED_CLINICIAN finding closes no sheet,
 * snaps no transient and leaves the presence orb as it was.
 */
import type { RedLocation, RedPresentation, RedRegister } from "../livekit/red";

/** Every register the schema defines, in 02 §5.3's order. */
export const RED_REGISTERS = [
  "ALERT",
  "CALM",
  "SILENT",
  "DEFERRED_CLINICIAN",
] as const satisfies readonly RedRegister[];

/** Every location the schema defines. */
export const RED_LOCATIONS = [
  "REMOTE",
  "ON_SITE",
  "UNKNOWN",
] as const satisfies readonly RedLocation[];

/**
 * Where a RED's first paint happens:
 * - `rootLayer`: a layer above the navigators, mounted by the signed-in
 *   shell as a sibling after the navigator container. No navigation call.
 * - `inFlow`: in the session's own stream, where the next turn would be.
 * - `none`: nothing on the patient's screen changes.
 */
export type RedPresentationMode = "rootLayer" | "inFlow" | "none";

/** How ALERT, CALM, SILENT and DEFERRED_CLINICIAN are first painted. */
export function redPresentationMode(register: RedRegister): RedPresentationMode {
  switch (register) {
    case "ALERT":
    case "CALM":
      return "rootLayer";
    case "SILENT":
      return "inFlow";
    case "DEFERRED_CLINICIAN":
      return "none";
  }
}

/**
 * The motion a RED carries. Every field is a literal type, so no caller can
 * build a RED that moves: the compiler refuses the object before a test
 * would.
 */
export interface RedMotion {
  readonly enterMs: 0;
  readonly delayMs: 0;
  readonly exitMs: 0;
  readonly loop: false;
  readonly flash: false;
  readonly stagger: false;
  /** No timed exit: a RED stays until the patient acts on it. */
  readonly autoDismissMs: null;
  /** No swipe, back-swipe or pull closes it. */
  readonly dismissByGesture: false;
  readonly haptic: false;
  /** Actions commit on press; feedback is instant; nothing needs a long-press. */
  readonly actions: {
    readonly commitOn: "press";
    readonly feedbackMs: 0;
    readonly longPress: false;
  };
}

const RED_MOTION: RedMotion = {
  enterMs: 0,
  delayMs: 0,
  exitMs: 0,
  loop: false,
  flash: false,
  stagger: false,
  autoDismissMs: null,
  dismissByGesture: false,
  haptic: false,
  actions: { commitOn: "press", feedbackMs: 0, longPress: false },
};

/** What the rest of the screen does in the commit that presents a RED. */
export interface RedYield {
  /** Every running transient jumps to its end state (the arbiter's snap). */
  readonly snapTransients: boolean;
  /** The ambient loop stops. Only RED stops it; everything else holds it. */
  readonly stopAmbient: boolean;
  /** Any open RN `Modal` closes in this commit, its `animationType` already `"none"`. */
  readonly closeModals: boolean;
  /** The presence orb: gone under a takeover, still at idle beside SILENT guidance. */
  readonly orb: "unmount" | "idle" | "unchanged";
}

const YIELDS: Readonly<Record<RedPresentationMode, RedYield>> = {
  rootLayer: { snapTransients: true, stopAmbient: true, closeModals: true, orb: "unmount" },
  inFlow: { snapTransients: true, stopAmbient: true, closeModals: true, orb: "idle" },
  none: { snapTransients: false, stopAmbient: false, closeModals: false, orb: "unchanged" },
};

/** The patient's answer to the one location question (UNKNOWN only). */
export type LocationAnswer = "unanswered" | "inHospital" | "notInHospital";

/** The location-dependent controls a RED mounts. */
export interface RedAffordances {
  /** The 112 control (large selectable text and `tel:`, 02 §5.3). */
  readonly call112: boolean;
  /** The one question, "Şu anda hastanede misiniz?", with its two answers. */
  readonly askLocation: boolean;
}

const NOTHING: RedAffordances = { call112: false, askLocation: false };

/**
 * The location controls for one RED, given the answer so far. The answer is
 * read only under UNKNOWN; REMOTE and ON_SITE are known and never asked.
 */
export function redAffordances(
  presentation: RedPresentation,
  answer: LocationAnswer,
): RedAffordances {
  if (redPresentationMode(presentation.register) === "none") {
    return NOTHING;
  }
  // `show112` is the pack's authorisation, clamped for ON_SITE upstream.
  // It can only narrow what the location allows.
  const authorised = presentation.show112;
  switch (presentation.location) {
    case "ON_SITE":
      return NOTHING;
    case "REMOTE":
      return { call112: authorised, askLocation: false };
    case "UNKNOWN":
      if (answer === "unanswered") {
        return { call112: false, askLocation: true };
      }
      return { call112: answer === "notInHospital" && authorised, askLocation: false };
  }
}

export interface RedContext {
  /** The patient's reduce-motion answer. A RED ignores it: it has no motion to reduce. */
  readonly reduce: boolean;
}

/** Everything a RED's first frame depends on, decided before that frame. */
export interface RedFirstPaint {
  readonly mode: RedPresentationMode;
  readonly motion: RedMotion;
  readonly yields: RedYield;
  readonly affordances: RedAffordances;
}

/**
 * The first paint of one RED. It depends on the presentation alone — never on
 * audio, a navigator, a UIKit presentation, a haptic, the arbiter or the
 * microphone teardown — so motion adds nothing to 02 §8.1's 300 ms.
 */
export function redFirstPaint(presentation: RedPresentation, context: RedContext): RedFirstPaint {
  const mode = redPresentationMode(presentation.register);
  return {
    mode,
    motion: RED_MOTION,
    yields: YIELDS[mode],
    affordances: redAffordances(presentation, "unanswered"),
  };
}
