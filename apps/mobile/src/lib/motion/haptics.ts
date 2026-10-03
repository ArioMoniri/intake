/**
 * The haptic policy (INT-340, MOTION-11; docs/design/motion/motion-verification.md
 * §2.1 #9–#11, §4 MOTION-11; ADR-033 §6; motion-system-spec.md §6.1).
 *
 * Pure — no React Native, no native module — so the whole policy is
 * node-testable. The live half, which reads the session and the microphone at
 * fire time, is ./hapticGate.ts; the device half is native/hapticsEngine.ts.
 *
 * A haptic fires only if ALL of these hold, and each is read as "blocked"
 * unless it is exactly `false` (a missing or unknown answer fails closed):
 * - the voice session is not active, and the microphone is not hot. Apple's
 *   guidance is that haptics must not disrupt the microphone (HIG, Playing
 *   haptics); a buzz is also picked up by the recording it interrupts;
 * - no RED is presented. No register fires a haptic of its own either: there
 *   is no event a RED could ask with (ADR-033 Q2's fail-closed default);
 * - nothing in this session has made silence permanent. After a SILENT RED
 *   or a third party, a buzz on the table is the cue 02 §5.3 names (S-3);
 * - the surface owns the event (`SURFACE_EVENTS`). Consent, legal text,
 *   errors and validated instrument options own none. A consent grant and its
 *   withdrawal feel the same because neither is felt (P4). An answer chip and
 *   the composer mic own the selection tick (ADR-038 A2, owner, 3 Oct 2026):
 *   every option ticks the same, so no answer is rewarded over another (P17);
 * - `select` only on a real change, and `success` only when the server has
 *   confirmed the outcome, never on the press that asked for it (P12, P13).
 *
 * What it returns is a `HapticCall`, a union with no member that could mean an
 * error, a warning or a heavy impact. On iOS that is the selection tick, the
 * light impact and the success notification (UIFeedbackGenerator, which stays
 * silent when the patient turns System Haptics off). On Android it is only
 * `performAndroidHapticsAsync` (View.performHapticFeedback, which follows the
 * touch-feedback setting and needs no VIBRATE permission) with the constants
 * AOSP maps to a tick or a click — never REJECT, and never LONG_PRESS or
 * DRAG_START, which it maps to a heavy click. A haptic is never the only
 * feedback: every event pairs with a visual already on screen.
 */

/** The complete event list (motion-system-spec.md §6.1). Nothing else is ever felt. */
export type HapticEvent = "select" | "toggleOn" | "toggleOff" | "arm" | "success";

export const HAPTIC_EVENTS: readonly HapticEvent[] = [
  "select",
  "toggleOn",
  "toggleOff",
  "arm",
  "success",
];

/** `other` is every platform without a haptic engine (the web build). */
export type HapticPlatform = "ios" | "android" | "other";

/**
 * The RED registers the gate holds haptics for, spelled as livekit's
 * `RedRegister`. It is declared here rather than imported so that the gate
 * never imports the RED path: e2e/motion.spec.ts's MOTION-4 scan pins every
 * file that does and forbids a haptic in it, and the gate is the one module
 * whose job is to name haptics. haptics.test.ts proves the two types equal, so
 * they cannot drift.
 */
export type GateRedRegister = "ALERT" | "CALM" | "SILENT" | "DEFERRED_CLINICIAN";

/**
 * Where a request comes from. The first five are the wired surfaces; the last
 * four are named so that a screen can say what it is and be refused.
 */
export type HapticSurface =
  | "settings"
  | "visits"
  | "shareIssue"
  | "shareRevoke"
  | "dsar"
  | "consent"
  | "legal"
  | "error"
  | "intakeChip"
  | "dialogueMic"
  | "instrumentOption";

/**
 * The events each surface may fire:
 * - `settings`: Görünüm's segmented options and its settings switch rows;
 * - `visits`: the list/calendar switch and a calendar day;
 * - `shareIssue` / `shareRevoke`: the same server-confirmed `success` both
 *   ways, and `arm` on the revoke's first tap (its two-step);
 * - `dsar`: `arm` on the erasure's first tap, `success` when a request is
 *   recorded or withdrawn.
 */
export const SURFACE_EVENTS: { readonly [S in HapticSurface]: readonly HapticEvent[] } = {
  settings: ["select", "toggleOn", "toggleOff"],
  visits: ["select"],
  shareIssue: ["success"],
  shareRevoke: ["arm", "success"],
  dsar: ["arm", "success"],
  consent: [],
  legal: [],
  error: [],
  // ADR-038 A2 (INT-462): the same tick for every option, so no answer is
  // rewarded over another; the live gate still refuses it while speech plays,
  // the mic is hot, a RED shows or a session has gone silent.
  intakeChip: ["select"],
  // The tap on the composer mic that opens the microphone, before it opens.
  dialogueMic: ["select"],
  // A validated instrument is administered as validated: never felt.
  instrumentOption: [],
};

export const HAPTIC_SURFACES = Object.keys(SURFACE_EVENTS) as readonly HapticSurface[];

/** iOS: the selection tick, the lightest impact and the success notification. */
export type IosHapticCall =
  | { readonly platform: "ios"; readonly method: "selectionAsync" }
  | { readonly platform: "ios"; readonly method: "impactAsync"; readonly style: "light" }
  | { readonly platform: "ios"; readonly method: "notificationAsync"; readonly type: "success" };

/** The `AndroidHaptics` values used, spelled as the module's enum spells them. */
export type AndroidHapticType =
  "segment-tick" | "toggle-on" | "toggle-off" | "context-click" | "confirm";

/** Android: View.performHapticFeedback only, never the Vibrator. */
export interface AndroidHapticCall {
  readonly platform: "android";
  readonly method: "performAndroidHapticsAsync";
  readonly type: AndroidHapticType;
}

export type HapticCall = IosHapticCall | AndroidHapticCall;

/** Everything the policy needs, read at fire time by the gate. */
export interface HapticContext {
  readonly platform: HapticPlatform;
  readonly voiceSessionActive: boolean;
  readonly micHot: boolean;
  readonly redPresented: boolean;
  /** Sticky: set once a SILENT RED or a third party occurred, never cleared in the session. */
  readonly silentOrThirdPartyThisSession: boolean;
  readonly surface: HapticSurface;
  /** `select` only: the chosen value differs from the one before. */
  readonly valueChanged?: boolean;
  /** `success` only: the server has confirmed the outcome. */
  readonly serverConfirmed?: boolean;
}

/** The context without the platform: what the gate can decide before the engine loads. */
export type HapticGateContext = Omit<HapticContext, "platform">;

const IOS: { readonly [E in HapticEvent]: IosHapticCall } = {
  select: { platform: "ios", method: "selectionAsync" },
  toggleOn: { platform: "ios", method: "selectionAsync" },
  toggleOff: { platform: "ios", method: "selectionAsync" },
  arm: { platform: "ios", method: "impactAsync", style: "light" },
  success: { platform: "ios", method: "notificationAsync", type: "success" },
};

const ANDROID: { readonly [E in HapticEvent]: AndroidHapticType } = {
  select: "segment-tick",
  toggleOn: "toggle-on",
  toggleOff: "toggle-off",
  arm: "context-click",
  success: "confirm",
};

function eventsOf(surface: string): readonly HapticEvent[] {
  return Object.prototype.hasOwnProperty.call(SURFACE_EVENTS, surface)
    ? SURFACE_EVENTS[surface as HapticSurface]
    : [];
}

/** Whether `event` may fire in `ctx`, whatever the platform. */
export function hapticAllowed(event: HapticEvent, ctx: HapticGateContext): boolean {
  if (
    ctx.voiceSessionActive !== false ||
    ctx.micHot !== false ||
    ctx.redPresented !== false ||
    ctx.silentOrThirdPartyThisSession !== false
  ) {
    return false;
  }
  if (!eventsOf(ctx.surface).includes(event)) {
    return false;
  }
  if (event === "select" && ctx.valueChanged !== true) {
    return false;
  }
  if (event === "success" && ctx.serverConfirmed !== true) {
    return false;
  }
  return true;
}

/** The one call for `event` in `ctx`, or `null`: nothing is felt. */
export function hapticFor(event: HapticEvent, ctx: HapticContext): HapticCall | null {
  if (!hapticAllowed(event, ctx)) {
    return null;
  }
  if (ctx.platform === "ios") {
    return { ...IOS[event] };
  }
  if (ctx.platform === "android") {
    return { platform: "android", method: "performAndroidHapticsAsync", type: ANDROID[event] };
  }
  return null;
}
