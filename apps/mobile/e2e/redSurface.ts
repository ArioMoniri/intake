/**
 * What a source file says about the RED path, for e2e/motion.spec.ts's
 * MOTION-4 guard (INT-333; docs/design/motion/motion-verification.md §4
 * MOTION-4, System R3: "the scan must pin the list of RED surface files, so
 * that it is never vacuous").
 *
 * A file is a RED surface when it holds the RED contract, reads a RED
 * presentation, handles the session's `red` event or paints with the
 * RED-reserved colour. The spec pins the exact set, so a file INT-135 adds
 * for the RED UI is found here and must be named there, and every named file
 * is scanned. React Native has no DOM, so these read the source, with its
 * comments removed (./motionSource `code`).
 *
 * The names this module looks for are assembled from parts, so it never
 * spells what the app-wide guards scan for.
 */
import { code } from "./motionSource";

/** `import … from "<m>"`, `export … from "<m>"`, `import("<m>")`, `require("<m>")`. */
const SPECIFIER =
  /\b(?:import|export)\s+(?:type\s+)?[^;]*?\bfrom\s*["']([^"']+)["']|\b(?:import|require)\s*\(\s*["']([^"']+)["']\s*\)/g;

export function specifiers(source: string): string[] {
  return [...code(source).matchAll(SPECIFIER)].map((m) => m[1] ?? m[2]);
}

/** The two modules that hold the RED contract: decoding and motion. */
export const RED_CONTRACT = ["src/lib/livekit/red.ts", "src/lib/motion/red.ts"] as const;

const RED_MODULE = /(?:^|\/)red$/;
const RED_NAMES =
  /\b(?:RedPresentation|redFirstPaint|redPresentationMode|redAffordances|resolveRed|decodeRedTrigger)\b/;
const RED_EVENT = /\btype\s*===\s*["']red["']|\bcase\s+["']red["']\s*:/;
const RED_COLOUR = new RegExp(`\\.\\s*${["emer", "gency"].join("")}(?:Soft)?\\b`);

/** Whether a file belongs to the RED path, by any of the four routes in. */
export function isRedSurface(source: string): boolean {
  const text = code(source);
  return (
    specifiers(source).some((s) => RED_MODULE.test(s)) ||
    RED_NAMES.test(text) ||
    RED_EVENT.test(text) ||
    RED_COLOUR.test(text)
  );
}

const REANIMATED = ["react-native", "reanimated"].join("-");
const HAPTICS_MODULE = ["expo", "haptics"].join("-");
const ROUTER_MODULE = ["expo", "router"].join("-");
const NAVIGATION_MODULE = ["@react", "navigation"].join("-");

/** Each thing a first paint must never touch, with how it looks in code. */
const FORBIDDEN: readonly (readonly [string, RegExp])[] = [
  [
    "animation API",
    new RegExp(
      [
        `\\b${["Anim", "ated"].join("")}\\b`,
        `\\b(?:with${["Tim", "ing"].join("")}|withRepeat|withDelay|withSequence|withDecay)\\b`,
        `\\b(?:FadeIn|FadeOut|Keyframe|useAnimatedStyle|useSharedValue)\\b`,
        `\\b(?:entering|exiting)\\s*=`,
        `\\b${["Layout", "Animation"].join("")}\\b`,
        `\\b(?:cssFade|enterFor|enteringFor|fadeSpec)\\b`,
        `\\brequestAnimationFrame\\b`,
      ].join("|"),
    ),
  ],
  ["haptics", new RegExp(`\\b(?:Haptics|Vibration|hapticFor)\\b`)],
  ["Modal", /\bModal\b|\banimationType\b/],
  [
    "router call",
    /\buseRouter\b|\brouter\s*\.\s*\w+\s*\(|\bnavigation\s*\.\s*\w+\s*\(|<\s*(?:Link|Redirect)\b/,
  ],
];

const FORBIDDEN_MODULES: readonly (readonly [string, RegExp])[] = [
  ["animation API", new RegExp(`^${REANIMATED}(?:/|$)`)],
  ["haptics", new RegExp(`^${HAPTICS_MODULE}$`)],
  ["router call", new RegExp(`^(?:${ROUTER_MODULE}|${NAVIGATION_MODULE}/)`)],
  ["animation API", /(?:^|\/)motion\/(?:fade|transients|native\/[\w]+)$/],
];

/** Every forbidden thing a RED surface file reaches, by name. */
export function firstPaintViolations(source: string): string[] {
  const text = code(source);
  const direct = FORBIDDEN.filter(([, pattern]) => pattern.test(text)).map(([name]) => name);
  const imported = specifiers(source).flatMap((s) =>
    FORBIDDEN_MODULES.filter(([, pattern]) => pattern.test(s)).map(([name]) => name),
  );
  return [...new Set([...direct, ...imported])].sort();
}

/** The body of `const <name> = (…) => { … };` in `source`, or null. */
export function arrowBody(source: string, name: string): string | null {
  const text = code(source);
  const head = new RegExp(`const\\s+${name}\\s*=\\s*(async\\s*)?\\([^)]*\\)\\s*=>\\s*\\{`).exec(
    text,
  );
  if (head === null) {
    return null;
  }
  const open = head.index + head[0].length - 1;
  let depth = 0;
  for (let i = open; i < text.length; i += 1) {
    if (text[i] === "{") {
      depth += 1;
    } else if (text[i] === "}") {
      depth -= 1;
      if (depth === 0) {
        return (head[1] ?? "") + text.slice(open, i + 1);
      }
    }
  }
  return null;
}

/** What makes a handler wait: an await, a promise chain, a timer, a frame. */
export const WAITS =
  /\bawait\b|\basync\b|\.\s*then\s*\(|\bsetTimeout\b|\bsetInterval\b|\bsleep\s*\(|\brequestAnimationFrame\b/;
