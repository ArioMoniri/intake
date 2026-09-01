/**
 * Appearance preferences (INT-260) — the policy, as pure functions.
 *
 * The owner asked for adjustable text size and settings. Four things are
 * adjustable here, and each one had to have a real consumer before it earned
 * a control: text size (`useFontScale`), theme (`useScheme`), on-screen
 * motion (`useReducedMotion`) and how a visit starts (the intake shell's
 * voice-eligibility rule). A switch whose value nothing reads is decoration
 * with a nice pill on it (invariant 17), so nothing else is offered yet —
 * spoken reading is a dialogue-surface preference and lands with that surface.
 *
 * No react-native import, so every rule below is testable in node — the same
 * split lib/theme.ts uses. `AppearanceProvider.tsx` is the thin React and
 * storage adapter; this file is what the tests hold.
 *
 * ─────────────────────────────────────────────────────────────────────────
 * Data inventory (CLAUDE.md invariant 18), for the whole record below:
 *
 *   category:   device preference (not personal data; no identifier, no
 *               clinical content, not linked to an account)
 *   purpose:    accessibility — legibility, contrast and motion tolerance
 *   basis:      contract (performing the service the patient asked for)
 *   retention:  until uninstall, or until the patient resets it
 *   recipients: none — it is written to this device's keychain slot with
 *               WHEN_UNLOCKED_THIS_DEVICE_ONLY, so it does not reach a
 *               server, an analytics sink, an iCloud backup, or the
 *               patient's other devices
 *
 * That annotation is not self-approval. Persisting a NEW category of
 * patient-controlled state is stop-and-ask under CLAUDE.md, and the ask is
 * filed for the DPO/counsel owner in docs/backlog/blockers.md with the one
 * sentence they must answer. The mechanism is built and fails safe meanwhile
 * (HUMAN_BLOCKERS.md rule 2): a record that cannot be read, or that carries a
 * value this file does not recognise, yields the device-following defaults.
 * ─────────────────────────────────────────────────────────────────────────
 */
import type { ColorScheme } from "../theme";

/**
 * The five sizes the control offers (design plan R5 — discrete, never a
 * slider). `typeScale` is seven fixed integers and `scaledSize` rounds, so a
 * continuous control would promise precision the token system does not have.
 *
 * The ladder spans theme.ts's [0.5, 2.0] clamp at the top on purpose: if it
 * stopped short, a patient already at OS 2.0 who touched the control would
 * lose size, and the control would be worse than no control.
 */
export const APP_STEPS = [0.9, 1.0, 1.3, 1.6, 2.0] as const;

/** An index into APP_STEPS. `null` is a fifth state: follow the phone. */
export type TextStep = 0 | 1 | 2 | 3 | 4;

export type ThemePref = "system" | "light" | "dark";

/** How a fresh visit opens: the spoken dialogue, or the typed steps. */
export type StartMode = "voice" | "typed";

export interface AppearancePrefs {
  /** `null` — and it is the default — means the OS setting is the setting. */
  readonly textStep: TextStep | null;
  readonly theme: ThemePref;
  /** ORed with the OS signal; it can add reduced motion, never remove it. */
  readonly reduceMotion: boolean;
  readonly startMode: StartMode;
}

/**
 * Follow the device wherever the device has an answer. A first-run patient
 * who set Dynamic Type or "Hareketi Azalt" in iOS must find the app already
 * obeying it — the control exists for the patient the OS setting did not
 * reach, not to introduce a second place the same question is asked.
 */
export const DEFAULT_APPEARANCE: AppearancePrefs = {
  textStep: null,
  theme: "system",
  reduceMotion: false,
  startMode: "voice",
};

/**
 * The keychain slot. Versioned so a future shape change reads nothing rather
 * than mis-reading an old record into a state the screen cannot show.
 */
export const APPEARANCE_SLOT = "intake.appearance.v1";

/**
 * The scale at which a screen changes FORM (00 §2, theme.ts:175-179): the tab
 * rail drops its captions, and the segmented control stacks. One threshold,
 * one function, two consumers — so the rail and the control can never
 * disagree about what "large text" means.
 */
export const LARGE_TEXT_SCALE = 1.6;

export function isLargeText(effectiveScale: number): boolean {
  return effectiveScale >= LARGE_TEXT_SCALE;
}

/**
 * The largest scale at which the floating tab rail can still show its five
 * captions — and it is LOWER than the content threshold above.
 *
 * theme.ts claimed the rail collapsed at 1.6 from INT-130 onward and nothing
 * implemented it, so the number was never tested against a phone. Measured on
 * the simulator at 1.3: the `micro` caption renders at 14 pt, five Turkish
 * labels do not fit the pill, and "Profilim" clipped mid-word. The rail is the
 * tightest horizontal box in the app — five fixed items, no wrapping, no
 * scrolling — so it gets its own number rather than borrowing the one that
 * governs content.
 */
export const RAIL_LABEL_MAX_SCALE = 1.2;

export function railCollapses(effectiveScale: number): boolean {
  return effectiveScale > RAIL_LABEL_MAX_SCALE;
}

/**
 * The rail glyph's base size at scale 1.0 — the measured Oura rail item
 * (design pass 5); 22 read one register too loud.
 */
export const RAIL_GLYPH_BASE = 20;

/** Padding around the glyph inside its well, so the well is a target. */
const RAIL_WELL_PADDING = 16;

/**
 * The rail's item box at a given scale, and the ONE source for it.
 *
 * Both the rail and the scroll clearance below it read this: the owner's
 * report was that content ran underneath the navbar, which happens whenever
 * the chrome's height and the padding reserved for it are two numbers that can
 * drift. Never below MIN_TAP, whatever the glyph does (SC 2.5.8).
 */
export function railWellSize(effectiveScale: number, minimum: number): number {
  const clamped = Math.max(0.5, Math.min(effectiveScale, 2.0));
  return Math.max(minimum, Math.round(RAIL_GLYPH_BASE * clamped) + RAIL_WELL_PADDING);
}

/**
 * The widest inline segmented group a phone holds with Turkish labels.
 *
 * Measured rather than guessed: at OS 1.0 on a 402 pt screen, five labels in
 * one row put "Daha büyük" and "En büyük" onto two lines each and left the
 * pills at different heights. Four or more options therefore stack at EVERY
 * scale; three or fewer stack only once the text is large.
 */
export const MAX_INLINE_OPTIONS = 3;

export function shouldStack(effectiveScale: number, optionCount: number): boolean {
  return isLargeText(effectiveScale) || optionCount > MAX_INLINE_OPTIONS;
}

/**
 * The app's text scale: the chosen step REPLACES the OS value.
 *
 * Not composition (design plan R4). Multiplying the two is precisely what
 * `allowFontScaling={false}` exists to prevent — and with theme.ts's [0.5,
 * 2.0] clamp on top of it, a patient already at OS 2.0 would get a control
 * where every step renders the same size. Replacement keeps all five steps
 * distinct at every OS setting, and keeps "text scales once, never twice"
 * true by construction rather than by care.
 */
export function effectiveFontScale(textStep: TextStep | null, osFontScale: number): number {
  return textStep === null ? osFontScale : APP_STEPS[textStep];
}

/**
 * The rung closest to a scale the patient is already reading.
 *
 * Used when "Telefon ayarını kullanın" is switched off: the switch changes
 * WHERE the size comes from, and must not change the size out from under the
 * finger that touched it. A tie rounds UP, because an accessibility control
 * that guesses smaller has guessed wrong.
 */
export function nearestStep(osFontScale: number): TextStep {
  // The tolerance is what makes the round-up rule real. 1.15 sits exactly
  // between two rungs in decimal and NOT in binary — (1.3 - 1.15) is larger
  // than (1.15 - 1.0) by one ulp — so an exact comparison rounds the midpoint
  // DOWN, which is the one direction an accessibility control must never take.
  const TIE = 1e-9;
  let best: TextStep = 0;
  let bestGap = Number.POSITIVE_INFINITY;
  for (let index = 0; index < APP_STEPS.length; index += 1) {
    const gap = Math.abs(APP_STEPS[index] - osFontScale);
    if (gap <= bestGap + TIE) {
      best = index as TextStep;
      bestGap = Math.min(gap, bestGap);
    }
  }
  return best;
}

/** The palette to render: an explicit choice wins, `system` asks the OS. */
export function resolveScheme(pref: ThemePref, osScheme: string | null | undefined): ColorScheme {
  if (pref === "system") {
    return osScheme === "dark" ? "dark" : "light";
  }
  return pref;
}

/**
 * OR, deliberately, and not an override in either direction: the app switch
 * can ADD reduced motion for a patient whose OS setting missed it, and can
 * never take it away from a patient who asked the OS for it.
 */
export function reducedMotion(appOverride: boolean, osReduced: boolean): boolean {
  return appOverride || osReduced;
}

function isTextStep(value: unknown): value is TextStep {
  return (
    typeof value === "number" && Number.isInteger(value) && value >= 0 && value < APP_STEPS.length
  );
}

/**
 * Read a stored record.
 *
 * Every field is validated on its own and falls back on its own, and an
 * out-of-ladder step is REFUSED rather than clamped: clamping would move the
 * patient to a size they never chose and give them no way to see that it had
 * happened. The device-local record is the only copy, so it must never be
 * able to put the app into a state the screen cannot render or undo.
 */
export function decodeAppearance(raw: string | null): AppearancePrefs {
  let parsed: unknown;
  try {
    parsed = raw === null ? null : JSON.parse(raw);
  } catch {
    return DEFAULT_APPEARANCE;
  }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    return DEFAULT_APPEARANCE;
  }
  const record = parsed as Record<string, unknown>;
  const theme = record.theme;
  const startMode = record.startMode;
  return {
    textStep: isTextStep(record.textStep) ? record.textStep : DEFAULT_APPEARANCE.textStep,
    theme:
      theme === "system" || theme === "light" || theme === "dark"
        ? theme
        : DEFAULT_APPEARANCE.theme,
    reduceMotion:
      typeof record.reduceMotion === "boolean"
        ? record.reduceMotion
        : DEFAULT_APPEARANCE.reduceMotion,
    startMode:
      startMode === "voice" || startMode === "typed" ? startMode : DEFAULT_APPEARANCE.startMode,
  };
}

/** Write a stored record — preferences only, and the test pins the key set. */
export function encodeAppearance(prefs: AppearancePrefs): string {
  return JSON.stringify({
    textStep: prefs.textStep,
    theme: prefs.theme,
    reduceMotion: prefs.reduceMotion,
    startMode: prefs.startMode,
  });
}
