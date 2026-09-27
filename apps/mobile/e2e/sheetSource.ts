/**
 * What the section sheet's source says about its motion and its focus, for
 * e2e/motion.spec.ts's MOTION-9 guard (INT-338;
 * docs/design/motion/motion-verification.md §4 MOTION-9, §1.1 C12, §1.2 P15,
 * CI note C-6).
 *
 * The policy is src/lib/motion/transitions.ts (`modalTransition`,
 * `sheetClose`), proved in its own suite. These read the wiring: React Native
 * has no DOM here, so they read the source, with its comments removed
 * (./motionSource `code`). Each finding names the half of the wiring that is
 * missing, so a failure says what broke.
 *
 * The one name another guard scans for (the app's reduce-motion hook) is
 * assembled from parts.
 */
import { closeOf, code, endOfString } from "./motionSource";
import { WAITS } from "./redSurface";

const HOOK = ["useReduced", "Motion"].join("");

/** One JSX opening tag. */
export interface Opening {
  /** Index of its `<`. */
  readonly start: number;
  /** Everything between the tag name and the closing `>` (or `/>`). */
  readonly props: string;
  /** Index just past its `>`. */
  readonly end: number;
  readonly selfClosing: boolean;
}

function escaped(name: string): string {
  return name.replace(/\./g, "\\.");
}

/** The first `<name …>` at or after `from`, read with braces and strings respected. */
export function openingOf(text: string, name: string, from = 0): Opening | null {
  const head = new RegExp(`<${escaped(name)}(?=[\\s/>])`, "g");
  head.lastIndex = from;
  const found = head.exec(text);
  if (found === null) {
    return null;
  }
  let depth = 0;
  for (let i = found.index + found[0].length; i < text.length; i += 1) {
    const c = text[i];
    if (c === '"' || c === "'" || c === "`") {
      i = endOfString(text, i);
    } else if ("{([".includes(c)) {
      depth += 1;
    } else if ("})]".includes(c)) {
      depth -= 1;
    } else if (c === ">" && depth === 0) {
      const selfClosing = text[i - 1] === "/";
      return {
        start: found.index,
        props: text.slice(found.index + found[0].length, selfClosing ? i - 1 : i),
        end: i + 1,
        selfClosing,
      };
    }
  }
  return null;
}

/** Every `<name …>` in `text`. */
export function openingsOf(text: string, name: string): Opening[] {
  const all: Opening[] = [];
  for (let at = openingOf(text, name); at !== null; at = openingOf(text, name, at.end)) {
    all.push(at);
  }
  return all;
}

/** What sits between an opening and its matching `</name>`, or null when it never closes. */
export function childrenOf(text: string, name: string, open: Opening): string | null {
  if (open.selfClosing) {
    return "";
  }
  const tag = new RegExp(`<${escaped(name)}(?=[\\s/>])|</${escaped(name)}>`, "g");
  tag.lastIndex = open.end;
  let depth = 1;
  for (let m = tag.exec(text); m !== null; m = tag.exec(text)) {
    if (m[0].startsWith("</")) {
      depth -= 1;
      if (depth === 0) {
        return text.slice(open.end, m.index);
      }
    } else {
      const inner = openingOf(text, name, m.index);
      if (inner === null) {
        return null;
      }
      depth += inner.selfClosing ? 0 : 1;
      tag.lastIndex = inner.end;
    }
  }
  return null;
}

/** `function name(…) { … }`: its parameter list and its body. */
export function functionOf(text: string, name: string): { params: string; body: string } | null {
  const head = new RegExp(`\\bfunction\\s+${name}\\s*\\(`).exec(text);
  if (head === null) {
    return null;
  }
  const open = head.index + head[0].length - 1;
  const close = closeOf(text, open);
  const body = text.indexOf("{", close);
  if (body < 0) {
    return null;
  }
  return { params: text.slice(open, close + 1), body: text.slice(body, closeOf(text, body) + 1) };
}

/** The whole text of every `name(…)` call in `text`. */
function callsOf(text: string, name: string): string[] {
  return [...text.matchAll(new RegExp(`\\b${name}\\s*\\(`, "g"))].map((m) => {
    const open = m.index + m[0].length - 1;
    return text.slice(m.index, closeOf(text, open) + 1);
  });
}

/** `const <name> = modalTransition({ reduce: <flag> })`. */
const TRANSITION = /\bconst\s+(\w+)\s*=\s*modalTransition\(\s*\{\s*reduce:\s*(\w+)\s*\}\s*\)/;

/** An exit animation, however it is registered: the prop, a props key, or a builder. */
const EXIT =
  /\bexiting\s*(?:=\s*\{|:)|\b(?:Fade|Slide|Zoom|Bounce|Flip|Stretch|Roll|Rotate|LightSpeed|Pinwheel)Out\w*\b/;

/**
 * Every `<Modal>` in one file whose presentation is not the policy's:
 * `animationType={<t>.animationType}` with `const <t> = modalTransition(…)`
 * in the same file, and never the reduce-motion primitive read directly.
 */
export function modalTypeFindings(source: string): string[] {
  const text = code(source);
  const transition = TRANSITION.exec(text);
  const policy =
    transition === null
      ? null
      : new RegExp(`^\\s*animationType=\\{\\s*${transition[1]}\\.animationType\\s*\\}`, "m");
  return openingsOf(text, "Modal")
    .filter((modal) => {
      const typed = /\banimationType=(?:\{[^}]*\}|"[^"]*")/.exec(modal.props);
      return (
        typed === null ||
        policy === null ||
        !policy.test(typed[0]) ||
        /\bmodalAnimation\s*\(/.test(text)
      );
    })
    .map(() => "animationType is not modalTransition's");
}

/**
 * Everything the section sheet's wiring is missing: the panel
 * (src/components/SectionPanel.tsx) and the dialogue that opens it
 * (src/components/DialogueIntake.tsx). Empty when it is whole.
 */
export function sheetFindings(panel: string, dialogue: string): string[] {
  const text = code(panel);
  const sheet = functionOf(text, "SectionSheet");
  if (sheet === null) {
    return ["no SectionSheet"];
  }
  const findings: string[] = [];
  const { body } = sheet;

  // The presentation: the policy's, fed by the app's reduce-motion hook.
  const transition = TRANSITION.exec(body);
  const fromHook =
    transition !== null &&
    new RegExp(`\\bconst\\s+${transition[2]}\\s*=\\s*${HOOK}\\(\\)`).test(body);
  const modal = openingOf(body, "Modal");
  if (modal === null || !fromHook || modalTypeFindings(panel).length > 0) {
    findings.push("animationType is not modalTransition's");
  }

  // One element enters: the Modal's only child is an Animated.View that
  // takes the policy's entrance and holds the backdrop and the panel both.
  const content = modal === null ? null : childrenOf(body, "Modal", modal);
  const wrapper = content === null ? null : openingOf(content, "Animated.View");
  const inside =
    content === null || wrapper === null ? null : childrenOf(content, "Animated.View", wrapper);
  const around =
    content === null || wrapper === null || inside === null
      ? null
      : content.slice(0, wrapper.start) +
        content.slice(wrapper.end + inside.length + "</Animated.View>".length);
  const entering =
    wrapper !== null &&
    transition !== null &&
    new RegExp(`\\bentering=\\{\\s*enteringFor\\(\\s*${transition[1]}\\.enter\\s*\\)\\s*\\}`).test(
      wrapper.props,
    );
  const holdsBoth =
    inside !== null &&
    openingsOf(inside, "Pressable").some((p) => /\bonPress=\{\s*onClose\s*\}/.test(p.props)) &&
    openingsOf(inside, "View").some((v) => /\baccessibilityViewIsModal\b/.test(v.props));
  const alone = around !== null && around.replace(/\{\s*\}/g, "").trim() === "";
  if (!entering || !holdsBoth || !alone) {
    findings.push("the content is not one element entering with modalTransition's fade");
  }

  // Exits are instant, and nothing else in the file animates in.
  if (EXIT.test(text)) {
    findings.push("an exit animation");
  }
  if ((text.match(/\bentering=/g) ?? []).length > 1) {
    findings.push("a second entrance");
  }

  // Focus goes back to the opener, in an effect keyed on `visible`, at once.
  const restoring = callsOf(body, "useEffect").filter(
    (effect) =>
      /\bsendAccessibilityEvent\(\s*\w+\s*,\s*["']focus["']\s*\)/.test(effect) &&
      /\bopener\.current\b/.test(effect) &&
      /,\s*\[[^\]]*\bvisible\b[^\]]*\]\s*\)$/.test(effect),
  );
  if (!/\bopener\b/.test(sheet.params) || restoring.length !== 1) {
    findings.push("focus is not returned to the opener");
  }
  if (restoring.some((effect) => WAITS.test(effect))) {
    findings.push("the focus return waits");
  }

  // The strip hands over the view the focus returns to…
  const strip = functionOf(text, "SectionStrip");
  const handsOver =
    strip !== null &&
    /\bref\b/.test(strip.params) &&
    openingsOf(strip.body, "Pressable").some((p) => /\bref=\{\s*ref\s*\}/.test(p.props));
  if (!handsOver) {
    findings.push("the strip does not hand over its view");
  }

  // …and the dialogue gives the sheet that same view as its opener.
  const opens = code(dialogue);
  const stripAt = openingOf(opens, "SectionStrip");
  const sheetAt = openingOf(opens, "SectionSheet");
  const handed = stripAt === null ? null : /\bref=\{\s*(\w+)\s*\}/.exec(stripAt.props);
  const wired =
    handed !== null &&
    sheetAt !== null &&
    new RegExp(`\\bopener=\\{\\s*${handed[1]}\\s*\\}`).test(sheetAt.props) &&
    new RegExp(`\\bconst\\s+${handed[1]}\\s*=\\s*useRef<View>\\(null\\)`).test(opens);
  if (!wired) {
    findings.push("the dialogue does not give the sheet the strip as its opener");
  }
  return findings;
}
