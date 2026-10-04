/**
 * Feature flags (INT-492, GitHub #839), as data.
 *
 * Pure, with no import, so src/lib/flags.test.ts holds every rule in node.
 * The build sets them: app.config.ts copies the build variable `INTAKE_FLAGS`
 * into `extra.flags`, and lib/featureFlags.ts is the one Expo-bound reader.
 *
 * - Off by default. A build nobody configured, or a value that is not a
 *   comma-separated list of known names, gives every flag off, so the app
 *   renders exactly what it rendered before the flag existed.
 * - Exact names only. An unknown name is ignored; it never switches a known
 *   one, and a near spelling is not a match.
 * - Approval needed. A flag that goes beyond the ratified motion and design
 *   ADRs (033, 037, 038, 039) is honoured in a development build only, so it
 *   can be shown to the owner and cannot reach a patient build before the
 *   owner approves it. Approving it is an ADR amendment and a change to
 *   APPROVAL_NEEDED here, never a build variable.
 */

/** Every flag the app knows. A closed list. */
export const FEATURE_FLAGS = ["progressMicro", "progressNumberRoll"] as const;

export type FeatureFlag = (typeof FEATURE_FLAGS)[number];

export type Flags = Readonly<Record<FeatureFlag, boolean>>;

/** Every flag off: the default for every build. */
export const FLAGS_OFF: Flags = Object.freeze({
  progressMicro: false,
  progressNumberRoll: false,
});

/**
 * - `progressMicro`: the question capsule, the chip check slot, the press
 *   response on the step's action and the send (ADR-037 P1), and the still
 *   loading glyph under Reduce Motion. All inside the ratified ADRs.
 * - `progressNumberRoll`: the capsule's number rolls its changed digits.
 *   ADR-033 §1 forbids count-up numerals and tickers, and on a step change it
 *   would be a second animated element beside the question's fade (§2, C9).
 */
export const APPROVAL_NEEDED: Readonly<Record<FeatureFlag, boolean>> = Object.freeze({
  progressMicro: false,
  progressNumberRoll: true,
});

/** A flag that only refines another needs that one on. */
const REQUIRES: Readonly<Partial<Record<FeatureFlag, FeatureFlag>>> = {
  progressNumberRoll: "progressMicro",
};

function isFeatureFlag(name: string): name is FeatureFlag {
  return (FEATURE_FLAGS as readonly string[]).includes(name);
}

/** The known names in a comma-separated value, in the order given, once each. */
export function parseFlagList(raw: unknown): FeatureFlag[] {
  if (typeof raw !== "string") {
    return [];
  }
  const names = raw
    .split(",")
    .map((name) => name.trim())
    .filter(isFeatureFlag);
  return [...new Set(names)];
}

/** The flags one build runs with. */
export function resolveFlags(raw: unknown, { dev }: { readonly dev: boolean }): Flags {
  const asked = new Set(parseFlagList(raw).filter((name) => dev || !APPROVAL_NEEDED[name]));
  const resolved: Record<FeatureFlag, boolean> = { ...FLAGS_OFF };
  for (const name of FEATURE_FLAGS) {
    const needs = REQUIRES[name];
    resolved[name] = asked.has(name) && (needs === undefined || asked.has(needs));
  }
  return Object.freeze(resolved);
}
