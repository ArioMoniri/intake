/**
 * What a source file says about looping, shared by the reduce-motion gate
 * (e2e/a11y.spec.ts BK14, BK15) and the Reanimated hygiene guards
 * (e2e/motion.spec.ts) so the two can never disagree about which files loop
 * (INT-335, MOTION-6; docs/design/motion/motion-verification.md §4 MOTION-6,
 * CI notes C-2 and C-3).
 *
 * It also holds the reader behind motion.spec's "animated styles touch only
 * opacity and transform", which needs a small object-literal parser.
 *
 * React Native has no DOM, so these read the source. They read it with its
 * comments removed: a doc comment that explains why a file does NOT loop
 * must not make it count as looping.
 */

/** Index of the quote that closes the string opened at `open`. */
function endOfString(source: string, open: number): number {
  const quote = source[open];
  let i = open + 1;
  while (i < source.length) {
    if (source[i] === "\\") {
      i += 2;
      continue;
    }
    if (source[i] === quote) {
      return i;
    }
    i += 1;
  }
  return source.length;
}

/**
 * The source without `//` and `/* … *\/` comments. Strings are kept whole, so
 * a URL inside one survives; a block comment keeps its newlines, so line
 * numbers do not move.
 */
export function code(source: string): string {
  let out = "";
  let i = 0;
  while (i < source.length) {
    const c = source[i];
    if (c === '"' || c === "'" || c === "`") {
      const end = endOfString(source, i);
      out += source.slice(i, end + 1);
      i = end + 1;
    } else if (c === "/" && source[i + 1] === "/") {
      const end = source.indexOf("\n", i);
      i = end < 0 ? source.length : end;
    } else if (c === "/" && source[i + 1] === "*") {
      const close = source.indexOf("*/", i + 2);
      const end = close < 0 ? source.length : close + 2;
      out += source.slice(i, end).replace(/[^\n]/g, "");
      i = end;
    } else {
      out += c;
      i += 1;
    }
  }
  return out;
}

/**
 * Every way the app could repeat an animation: core `Animated.loop`,
 * Reanimated's `withRepeat` (named at all: an aliased import still counts),
 * and a Reanimated CSS animation's iteration count.
 */
const LOOP = /\bAnimated\s*\.\s*loop\b|\bwithRepeat\b|\banimationIterationCount\b/;

export function loops(source: string): boolean {
  return LOOP.test(code(source));
}

/**
 * The value written for every duration: a `duration:` key, any `…Duration:`
 * key (a CSS animation or transition), and a layout-animation builder's
 * `.duration(…)`.
 */
const DURATION = /(?:\b\w*[dD]uration\s*:|\.duration\s*\()\s*([^,;)}\n]+)/g;

/** `motion.loop.pulsePeriodMs`, `motion.duration.fade`: a token read. */
const TOKEN = /\bmotion(?:\s*\.\s*\w+)+/g;

/**
 * Durations whose value is a number written in the file rather than read
 * from the motion tokens. A full-period token halved (`/ 2`) is still the
 * token; a name bound to a number literal in the same file is still a
 * literal. A duration computed by a policy function (`t.durationMs`) is not
 * a literal here: the policy module owns its own numbers and tests them.
 */
export function literalDurations(source: string): string[] {
  const text = code(source);
  const numericNames = new Set(
    [
      ...text.matchAll(/\b(?:const|let|var)\s+(\w+)\s*(?::\s*number\s*)?=\s*-?[\d.]+\s*[;,\n]/g),
    ].map((m) => m[1]),
  );
  return [...text.matchAll(DURATION)]
    .map((m) => m[1].trim())
    .filter((value) => {
      const rest = value.replace(TOKEN, "").replace(/\/\s*2\b/g, "");
      const names = rest.match(/\b[A-Za-z_$][\w$]*\b/g) ?? [];
      return /\d/.test(rest) || names.some((name) => numericNames.has(name));
    });
}

/** Index of the bracket that closes the one opened at `open`. */
function closeOf(text: string, open: number): number {
  let depth = 0;
  for (let i = open; i < text.length; i += 1) {
    const c = text[i];
    if (c === '"' || c === "'" || c === "`") {
      i = endOfString(text, i);
    } else if ("{[(".includes(c)) {
      depth += 1;
    } else if ("}])".includes(c)) {
      depth -= 1;
      if (depth === 0) {
        return i;
      }
    }
  }
  return text.length;
}

interface Entry {
  readonly key: string;
  /** Index where the entry's value begins; -1 for a shorthand or a spread. */
  readonly value: number;
}

/** Top-level entries of the object literal whose `{` sits at `open`. */
function objectEntries(text: string, open: number): Entry[] {
  const entries: Entry[] = [];
  const valueAt = (from: number) => {
    const colon = /^\s*:\s*/.exec(text.slice(from));
    return colon === null ? -1 : from + colon[0].length;
  };
  const end = closeOf(text, open);
  let depth = 0;
  let expectKey = false;
  for (let i = open; i < end; i += 1) {
    const c = text[i];
    if (c === '"' || c === "'" || c === "`") {
      const close = endOfString(text, i);
      if (depth === 1 && expectKey) {
        entries.push({ key: text.slice(i + 1, close), value: valueAt(close + 1) });
        expectKey = false;
      }
      i = close;
    } else if ("{[(".includes(c)) {
      depth += 1;
      expectKey = depth === 1;
    } else if ("}])".includes(c)) {
      depth -= 1;
    } else if (depth === 1 && c === ",") {
      expectKey = true;
    } else if (depth === 1 && expectKey && /\S/.test(c)) {
      const key = /^(\.\.\.\s*)?([A-Za-z_$][\w$]*|\d+)/.exec(text.slice(i));
      if (key !== null) {
        const spread = key[1] !== undefined;
        entries.push({
          key: spread ? `...${key[2]}` : key[2],
          value: spread ? -1 : valueAt(i + key[0].length),
        });
        i += key[0].length - 1;
      }
      expectKey = false;
    }
  }
  return entries;
}

/** A `transform` member names what it drives; driving one drives `transform`. */
const TRANSFORM_MEMBERS = new Set([
  "matrix",
  "perspective",
  "rotate",
  "rotateX",
  "rotateY",
  "rotateZ",
  "scale",
  "scaleX",
  "scaleY",
  "skewX",
  "skewY",
  "translateX",
  "translateY",
]);

/** A keyframe may carry its own curve; that is timing, not a style. */
const KEYFRAME_TIMING = new Set(["easing", "animationTimingFunction"]);

export function animatable(key: string): boolean {
  return (
    key === "opacity" ||
    key === "transform" ||
    TRANSFORM_MEMBERS.has(key) ||
    KEYFRAME_TIMING.has(key)
  );
}

export interface AnimatedKey {
  readonly site: string;
  readonly key: string;
}

/**
 * Every style key an app-authored animation drives in one file:
 * - each object a `useAnimatedStyle` worklet returns;
 * - a shared value, an `Animated.Value` or an interpolation of one, wherever
 *   a `style={…}` names it (a key, or a shorthand);
 * - each frame of a Reanimated CSS animation or `Keyframe`;
 * - a custom layout animation's `initialValues` and `animations`.
 */
export function animatedStyleKeys(source: string): AnimatedKey[] {
  const text = code(source);
  const found: AnimatedKey[] = [];
  const lineOf = (at: number) => text.slice(0, at).split("\n").length;
  const keysOf = (open: number, kind: string) => {
    for (const entry of objectEntries(text, open)) {
      found.push({ site: `${kind}:${lineOf(open)}`, key: entry.key });
    }
  };

  for (const call of text.matchAll(/\buseAnimatedStyle\s*\(/g)) {
    const open = call.index + call[0].length - 1;
    const body = text.slice(open, closeOf(text, open));
    for (const out of body.matchAll(/(?:\breturn|=>\s*\(|[?:])\s*\{/g)) {
      keysOf(open + out.index + out[0].length - 1, "useAnimatedStyle");
    }
  }

  const driven = new Set(
    [
      ...text.matchAll(
        /\b(?:const|let)\s+(\w+)\s*=\s*(?:useSharedValue|useDerivedValue|useAnimatedValue|(?:useRef\(\s*)?new\s+Animated\s*\.\s*Value(?:XY)?)\s*\(/g,
      ),
    ].map((m) => m[1]),
  );
  for (let grew = true; grew;) {
    grew = false;
    for (const m of text.matchAll(/\b(?:const|let)\s+(\w+)\s*=\s*(\w+)\s*\.\s*interpolate\s*\(/g)) {
      if (driven.has(m[2]) && !driven.has(m[1])) {
        driven.add(m[1]);
        grew = true;
      }
    }
  }
  for (const prop of text.matchAll(/\bstyle\s*=\s*\{/g)) {
    const open = prop.index + prop[0].length - 1;
    const expr = text.slice(open, closeOf(text, open) + 1);
    for (const id of driven) {
      const uses = [
        ...expr.matchAll(new RegExp(`([\\w$]+)\\s*:\\s*${id}\\b`, "g")),
        ...expr.matchAll(new RegExp(`[{,]\\s*(${id})\\s*(?=[,}])`, "g")),
      ];
      for (const use of uses) {
        found.push({ site: `style:${lineOf(open)}`, key: use[1] });
      }
    }
  }

  const frames = new Set<number>();
  for (const m of text.matchAll(
    /\banimationName\s*:\s*\{|\b(?:keyframes|new\s+Keyframe)\s*\(\s*\{/g,
  )) {
    frames.add(m.index + m[0].length - 1);
  }
  for (const m of text.matchAll(/\banimationName\s*:\s*(\w+)/g)) {
    const def = new RegExp(
      `\\b(?:const|let)\\s+${m[1]}\\b[^=]*=\\s*(?:[\\w.]*keyframes\\s*\\(\\s*|new\\s+Keyframe\\s*\\(\\s*)?\\{`,
    ).exec(text);
    if (def !== null) {
      frames.add(def.index + def[0].length - 1);
    }
  }
  for (const open of frames) {
    for (const frame of objectEntries(text, open)) {
      if (frame.value >= 0 && text[frame.value] === "{") {
        keysOf(frame.value, "keyframe");
      }
    }
  }

  for (const m of text.matchAll(/\b(?:initialValues|animations)\s*:\s*\{/g)) {
    keysOf(m.index + m[0].length - 1, "layout animation");
  }
  return found;
}
