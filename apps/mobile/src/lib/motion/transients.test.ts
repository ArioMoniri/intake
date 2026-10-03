/**
 * Typed-lane motion (INT-339, MOTION-10;
 * docs/design/motion/motion-verification.md §4 MOTION-10, and C14, C15 and
 * C16 of intake-voice-motion-spec.md).
 *
 * Four things are pinned here, all without a device:
 *
 * - the typed fallback (C15). When the typed steps replace the voice lane,
 *   their container fades in over the fade token, enter-only; under
 *   reduce-motion it is simply there. So the switch is fully visible within
 *   120 ms of the commit that makes it, far inside INT-135's 2 s, at every
 *   combination of the app switch and the OS answer;
 * - a step change (C16). The old question leaves in the commit that brings
 *   the next one, and only the next one fades in, so no frame holds two;
 * - completion (C14). No navigation in the app waits on an animation (a
 *   completion callback, a frame, a timer or the end of a transition), and
 *   the hand-over to the review is a plain call in a synchronous handler;
 * - the review screen renders every section in the commit that renders it:
 *   no stagger, no per-section delay, no incremental or virtualised list.
 *
 * The policy is pure and is called directly. React Native has no DOM here,
 * so its wiring into the screens is read from the source.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { describe, expect, it } from "vitest";

import { code } from "../../../e2e/motionSource";
import { packForVisit } from "../intake/questions";
import {
  voiceIntakeReducer,
  type VoiceIntakeAction,
  type VoiceIntakeState,
} from "../intake/voiceFirst";
import { reducedMotion } from "../prefs/appearance";
import { motion } from "../theme";
import { typedFallback, typedStep, type TypedStep } from "./transients";

const MOBILE = join(__dirname, "..", "..", "..");

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}

/** What ships: every script under src/, without its tests. */
const APP_SOURCE = walk(join(MOBILE, "src"))
  .filter((path) => /\.tsx?$/.test(path) && !/\.(test|spec)\.tsx?$/.test(path))
  .map((path) => ({
    name: relative(MOBILE, path).split(sep).join("/"),
    source: readFileSync(path, "utf8"),
  }));

function read(name: string): string {
  return readFileSync(join(MOBILE, name), "utf8");
}

const INTAKE = "src/app/(tabs)/visits/[visitId]/intake.tsx";
const REVIEW = "src/app/(tabs)/visits/[visitId]/review.tsx";
const DIALOGUE = "src/components/DialogueIntake.tsx";
const DIALOGUE_SESSION = "src/lib/dialogue/useDialogueSession.ts";

/** INT-135's acceptance: the typed fallback is visible within 2 s. */
const FALLBACK_BUDGET_MS = 2000;

const FADE = {
  property: "opacity",
  durationMs: motion.duration.fade,
  delayMs: 0,
  easing: motion.easing.out,
} as const;

/** Every reduce-motion setting: the app switch × the OS answer (null: none yet). */
const SETTINGS = [false, true].flatMap((app) =>
  [false, true, null].map((os) => ({ app, os, reduce: reducedMotion(app, os) })),
);

/* ------------------------------------------------------------------ */
/* Reading source: brackets, expressions, functions                    */
/* ------------------------------------------------------------------ */

/** Index of the quote that closes the string opened at `open`. */
function stringEnd(text: string, open: number): number {
  for (let i = open + 1; i < text.length; i += 1) {
    if (text[i] === "\\") {
      i += 1;
    } else if (text[i] === text[open]) {
      return i;
    }
  }
  return text.length;
}

/** From `start`, the index where an expression ends: `,` or `;` at depth 0, or an unmatched closer. */
function expressionEnd(text: string, start: number): number {
  let depth = 0;
  for (let i = start; i < text.length; i += 1) {
    const c = text[i];
    if (c === '"' || c === "'" || c === "`") {
      i = stringEnd(text, i);
    } else if ("([{".includes(c)) {
      depth += 1;
    } else if (")]}".includes(c)) {
      if (depth === 0) {
        return i;
      }
      depth -= 1;
    } else if (depth === 0 && (c === "," || c === ";")) {
      return i;
    }
  }
  return text.length;
}

/** Index of the bracket that closes the one opened at `open`. */
function closing(text: string, open: number): number {
  let depth = 0;
  for (let i = open; i < text.length; i += 1) {
    const c = text[i];
    if (c === '"' || c === "'" || c === "`") {
      i = stringEnd(text, i);
    } else if ("([{".includes(c)) {
      depth += 1;
    } else if (")]}".includes(c)) {
      depth -= 1;
      if (depth === 0) {
        return i;
      }
    }
  }
  return text.length;
}

interface Span {
  readonly start: number;
  readonly end: number;
}

interface Fn extends Span {
  readonly async: boolean;
}

/** Every arrow function and `function`, with its extent and whether it is async. */
function functionsIn(text: string): Fn[] {
  const arrows = [...text.matchAll(/=>\s*/g)].map((m) => {
    const body = m.index + m[0].length;
    const head = text.slice(Math.max(0, m.index - 160), m.index);
    return {
      start: m.index,
      end: text[body] === "{" ? closing(text, body) : expressionEnd(text, body),
      async: /\basync\s*(?:\([^()]*\)|[\w$]+)\s*(?::[^=()]*)?$/.test(head),
    };
  });
  const named = [...text.matchAll(/\b(async\s+)?function\b[^(]*\([^)]*\)[^{]*\{/g)].map((m) => ({
    start: m.index,
    end: closing(text, m.index + m[0].length - 1),
    async: m[1] !== undefined,
  }));
  return [...arrows, ...named];
}

/** The innermost function around `at`. */
function enclosingFunction(text: string, at: number): Fn | undefined {
  return functionsIn(text)
    .filter((f) => f.start < at && at <= f.end)
    .sort((a, b) => b.start - a.start)[0];
}

/* ------------------------------------------------------------------ */
/* What defers a call behind an animation                              */
/* ------------------------------------------------------------------ */

/**
 * Calls whose callback runs after an animation, a frame or a delay: core
 * Animated's `start(done)`, Reanimated's animation callbacks and a layout
 * animation's `withCallback`, the wait for running animations, a frame, a
 * timer, and a navigator's transition events.
 */
const DEFERRAL =
  /\.\s*start\s*\(|\bwith(?:Timing|Delay|Sequence|Repeat|Decay|Clamp)\s*\(|\.\s*withCallback\s*\(|\brunAfterInteractions\s*\(|\brequestAnimationFrame\s*\(|\bset(?:Timeout|Interval)\s*\(|\baddListener\s*\(\s*["'`]transition(?:Start|End)["'`]/g;

/** An animation or transition handler prop: `onAnimationEnd={…}`, `onTransitionEnd: …`. */
const HANDLER = /\bon(?:Animation|Transition)\w*\s*[=:]\s*/g;

/** An awaited wait: for running animations, a frame, a timer, or a sleep. */
const AWAITED_WAIT =
  /\brunAfterInteractions\b|\brequestAnimationFrame\b|\bset(?:Timeout|Interval)\b|\.\s*start\s*\(|\bwithCallback\b|\b(?:sleep|delay|wait)\s*\(/;

/** Every stretch of code that runs only after an animation, a frame or a delay. */
function deferredSpans(text: string): Span[] {
  const calls = [...text.matchAll(DEFERRAL)].map((m) => {
    const open = m.index + m[0].indexOf("(");
    return { start: open, end: closing(text, open) };
  });
  const handlers = [...text.matchAll(HANDLER)].map((m) => {
    const value = m.index + m[0].length;
    return {
      start: value,
      end: "{(".includes(text[value]) ? closing(text, value) : expressionEnd(text, value),
    };
  });
  const awaited = [...text.matchAll(/\bawait\b/g)]
    .filter((m) => AWAITED_WAIT.test(text.slice(m.index, expressionEnd(text, m.index))))
    .map((m) => ({ start: m.index, end: enclosingFunction(text, m.index)?.end ?? text.length }));
  return [...calls, ...handlers, ...awaited];
}

/** A navigation: expo-router's imperative API, or React Navigation's. */
const NAVIGATION =
  /\b(?:router|navigation)\s*\.\s*(?:push|replace|navigate|back|dismiss\w*|goBack|dispatch|reset|pop\w*)\s*\(/g;

/** Every call matching `target` that runs only after an animation, a frame or a delay. */
function chained(source: string, target: RegExp = NAVIGATION): string[] {
  const text = code(source);
  const spans = deferredSpans(text);
  return [...text.matchAll(new RegExp(target.source, "g"))]
    .filter((m) => spans.some((s) => s.start < m.index && m.index < s.end))
    .map((m) => `${text.slice(0, m.index).split("\n").length}: ${m[0]}`);
}

/* ------------------------------------------------------------------ */
/* Reading JSX                                                         */
/* ------------------------------------------------------------------ */

/** The source of the function component `name`, up to the next top-level function. */
function component(text: string, name: string): string {
  const start = text.indexOf(`function ${name}(`);
  expect(start, `function ${name}`).toBeGreaterThanOrEqual(0);
  const next = text.slice(start + 1).search(/\n(?:export\s+)?(?:default\s+)?function\s/);
  return next < 0 ? text.slice(start) : text.slice(start, start + 1 + next);
}

/** Each `<Tag …>…</Tag>` element, from its opening to its closing tag (not nested). */
function elements(text: string, tag: string): (Span & { readonly props: string })[] {
  return [...text.matchAll(new RegExp(`<${tag.replace(".", "\\.")}\\b([^>]*)>`, "g"))].map((m) => {
    const close = text.indexOf(`</${tag}>`, m.index);
    return { start: m.index, end: close < 0 ? text.length : close, props: m[1] };
  });
}

function inside(span: Span, at: number): boolean {
  return span.start < at && at < span.end;
}

/* ------------------------------------------------------------------ */
/* The step model                                                      */
/* ------------------------------------------------------------------ */

/**
 * The steps on screen `t` ms after the commit that replaces step `from` with
 * step `to` (t < 0 is the frame before it). A new key is a new element, so
 * React removes the old one in that commit; the only thing that keeps a
 * removed element on screen is an exit animation, for `exitMs`.
 */
function mountedAt(from: TypedStep, to: TypedStep, t: number): string[] {
  if (t < 0) {
    return [from.key];
  }
  if (to.key === from.key) {
    return [to.key];
  }
  return t < from.exitMs ? [from.key, to.key] : [to.key];
}

/** An exit animation, however it is registered: the prop, a props key, or a builder. */
const EXIT =
  /\bexiting\s*(?:=\s*\{|:)|\b(?:Fade|Slide|Zoom|Bounce|Flip|Stretch|Roll|Rotate|LightSpeed|Pinwheel)Out\w*\b/;

describe("MOTION-10 — the typed fallback (C15)", () => {
  it("fallback is enter-only and ≤ fadeMs", () => {
    const moving = typedFallback({ reduce: false });
    expect(moving).toEqual({ enter: FADE, exitMs: motion.duration.instant });
    expect(moving.enter!.durationMs).toBeLessThanOrEqual(motion.fadeMs);
    expect(moving.exitMs).toBe(0);
    // Under reduce-motion no entrance is registered: the steps are simply there.
    expect(typedFallback({ reduce: true })).toEqual({ enter: undefined, exitMs: 0 });

    // The steps' container takes that entrance, and only that one.
    const intake = code(read(INTAKE));
    const screen = component(intake, "TypedIntake");
    const container =
      /<Animated\.View\s+entering=\{enteringFor\(\s*(\w+)\.enter\s*\)\}[^>]*>\s*<StepFlow\b/.exec(
        screen,
      );
    expect(container, "StepFlow sits in an Animated.View entering from the plan").not.toBeNull();
    expect(screen).toMatch(
      new RegExp(`const ${container![1]} = typedFallback\\(\\{ reduce: (\\w+) \\}\\)`),
    );
    expect(screen).toMatch(/const (\w+) = useReducedMotion\(\);/);
    // A lane that is on screen first arrives with the route's own fade; only
    // a lane that replaces another one fades in.
    const skipping = elements(screen, "LayoutAnimationConfig").filter((e) =>
      /\bskipEntering\b/.test(e.props),
    );
    expect(skipping.some((e) => inside(e, container!.index))).toBe(true);
  });

  it("the fallback visible budget stays ≤ 2000 ms at every setting", () => {
    expect(SETTINGS).toHaveLength(6);
    for (const { app, os, reduce } of SETTINGS) {
      const { enter } = typedFallback({ reduce });
      const visibleMs = enter === undefined ? 0 : enter.delayMs + enter.durationMs;
      const setting = `app ${app}, os ${os}`;
      expect(visibleMs, setting).toBe(reduce ? 0 : motion.duration.fade);
      expect(visibleMs, setting).toBeLessThanOrEqual(motion.fadeMs);
      expect(visibleMs, setting).toBeLessThanOrEqual(FALLBACK_BUDGET_MS);
    }

    // The swap it times is one reducer step: every way out of the voice lane
    // lands in the steps at once, with no phase in between for motion to hold.
    const exits: readonly (readonly [VoiceIntakeState, VoiceIntakeAction])[] = [
      [{ phase: "dialogue" }, { type: "failure", prefill: {} }],
      [{ phase: "dialogue" }, { type: "candidates", prefill: {} }],
      [{ phase: "dialogue" }, { type: "skip" }],
      [{ phase: "gate" }, { type: "voice_unavailable" }],
      [{ phase: "gate" }, { type: "failure", prefill: {} }],
      [{ phase: "gate" }, { type: "skip" }],
    ];
    for (const [from, action] of exits) {
      expect(voiceIntakeReducer(from, action).phase, `${from.phase} + ${action.type}`).toBe(
        "steps",
      );
    }

    // The dialogue hands over from the effect that sees its terminal phase,
    // synchronously, and nothing on the way waits on an animation.
    const session = code(read(DIALOGUE_SESSION));
    for (const callback of [/\bonFailed\(/, /\bonHandoff\(/]) {
      const call = callback.exec(session.slice(session.indexOf('turn.phase === "done"')));
      expect(call, String(callback)).not.toBeNull();
      const at = session.indexOf('turn.phase === "done"') + call!.index;
      expect(enclosingFunction(session, at)?.async, String(callback)).toBe(false);
      expect(chained(read(DIALOGUE_SESSION), callback), String(callback)).toEqual([]);
    }
    expect(chained(read(INTAKE), /\bdispatchVoice\(/)).toEqual([]);
  });
});

describe("MOTION-10 — a typed step change (C16)", () => {
  it("a step change is enter-only and never shows two questions in one frame", () => {
    const pack = packForVisit(undefined, { mode: "detayli" });
    expect(pack.length).toBeGreaterThan(1);
    for (let i = 1; i < pack.length; i += 1) {
      const from = typedStep(pack[i - 1].id, { reduce: false });
      const to = typedStep(pack[i].id, { reduce: false });
      expect(to).toEqual({ key: pack[i].id, enter: FADE, exitMs: motion.duration.instant });
      expect(typedStep(pack[i].id, { reduce: true })).toEqual({
        key: pack[i].id,
        enter: undefined,
        exitMs: 0,
      });
      // Each question is its own element; a re-render of the same question
      // (a chip toggled) is the same element and never re-runs the entrance.
      expect(to.key).not.toBe(from.key);
      expect(typedStep(pack[i].id, { reduce: false }).key).toBe(to.key);
      for (let t = -1; t <= motion.duration.fade; t += 1) {
        expect(mountedAt(from, to, t), `${from.key} → ${to.key} at ${t} ms`).toEqual([
          t < 0 ? from.key : to.key,
        ]);
      }
    }

    // Exits are instant everywhere (motion-verification §2.1 #3): nothing in
    // the app registers the one thing that keeps a removed element on screen.
    for (const sample of [
      "<Animated.View exiting={FadeOut} />",
      "const props = { exiting: fade };",
      "const e = SlideOutLeft.duration(d);",
    ]) {
      expect(EXIT.test(code(sample)), sample).toBe(true);
    }
    expect(EXIT.test(code("<Animated.View entering={fade} />"))).toBe(false);
    expect(APP_SOURCE.filter((f) => EXIT.test(code(f.source))).map((f) => f.name)).toEqual([]);

    // The typed step's body is one element keyed by the question, entering
    // from the plan, under a skipEntering config so the first step arrives
    // with its container rather than fading a second time inside it.
    const flow = component(code(read(INTAKE)), "StepFlow");
    const bodies = elements(flow, "Animated.View");
    expect(bodies).toHaveLength(1);
    const [body] = bodies;
    const keyed = /^\s*key=\{(\w+)\.key\}\s+entering=\{enteringFor\(\s*\1\.enter\s*\)\}/.exec(
      body.props,
    );
    expect(keyed, "key={step.key} entering={enteringFor(step.enter)}").not.toBeNull();
    expect(flow).toMatch(
      new RegExp(`const ${keyed![1]} = typedStep\\(question\\.id, \\{ reduce: \\w+ \\}\\)`),
    );
    const skipping = elements(flow, "LayoutAnimationConfig").filter((e) =>
      /\bskipEntering\b/.test(e.props),
    );
    expect(skipping.some((e) => inside(e, body.start))).toBe(true);
    const at = (needle: string): number => {
      const index = flow.indexOf(needle);
      expect(index, needle).toBeGreaterThanOrEqual(0);
      return index;
    };
    // The question is inside it…
    expect(inside(body, at("t(question.titleKey)"))).toBe(true);
    expect(inside(body, at("question.options!.map"))).toBe(true);
    // …and the progress and the CTA are not: they swap instantly with the step (C9, C16).
    expect(inside(body, at("<QuestionProgress"))).toBe(false);
    const bars = [...flow.matchAll(/<GlassBar\b/g)];
    expect(bars.length).toBeGreaterThan(0);
    expect(bars.filter((m) => inside(body, m.index))).toEqual([]);
  });
});

describe("MOTION-10 — completion (C14)", () => {
  it("completion navigation is never chained to an animation", () => {
    const review = "router.replace(review)";
    for (const sample of [
      `Animated.timing(o, spec).start(() => ${review});`,
      `o.value = withTiming(1, spec, (done) => {\n  if (done) ${review};\n});`,
      `o.value = withDelay(d, withTiming(1, spec, () => router.push(r)));`,
      `const e = FadeIn.duration(d).withCallback(() => ${review});`,
      `InteractionManager.runAfterInteractions(() => ${review});`,
      "requestAnimationFrame(() => router.back());",
      `setTimeout(() => ${review}, motion.fadeMs);`,
      `navigation.addListener("transitionEnd", () => router.push(r));`,
      `<Animated.View onAnimationEnd={() => ${review}} />`,
      `async function finish() {\n  await InteractionManager.runAfterInteractions();\n  ${review};\n}`,
      `const finish = async () => {\n  await new Promise((r) => setTimeout(r, motion.fadeMs));\n  ${review};\n};`,
    ]) {
      expect(chained(sample), sample).toHaveLength(1);
    }
    // The same tick, a timer that navigates nowhere, and a wait that is not
    // an animation (the session's teardown) are not chains.
    expect(chained(`updateNote(id, done);\n${review};`)).toEqual([]);
    expect(chained("const t = setTimeout(() => setWait((s) => s - 1), 1000);")).toEqual([]);
    expect(chained(`const go = async () => {\n  await session.leave();\n  ${review};\n};`)).toEqual(
      [],
    );

    // No navigation anywhere in the app waits on an animation.
    const navigations = APP_SOURCE.flatMap((f) => [...code(f.source).matchAll(NAVIGATION)]);
    expect(navigations.length).toBeGreaterThan(20);
    const offenders = APP_SOURCE.flatMap((f) => chained(f.source).map((c) => `${f.name}:${c}`));
    expect(offenders).toEqual([]);

    // The typed lane and the dialogue reach the review with a plain call in
    // a synchronous handler, in the tick that finishes: the last commit, the
    // "Bitirdim" checkpoint, and the session's `done`.
    for (const name of [INTAKE, DIALOGUE]) {
      const text = code(read(name));
      const sites = [...text.matchAll(/\brouter\.replace\(\s*`[^`]*\/review`\s*\)/g)];
      expect(sites.length, name).toBeGreaterThan(0);
      for (const site of sites) {
        expect(enclosingFunction(text, site.index)?.async, `${name} @${site.index}`).toBe(false);
      }
    }
    const session = code(read(DIALOGUE_SESSION));
    const done = session.indexOf("onDone();");
    expect(done).toBeGreaterThan(0);
    expect(enclosingFunction(session, done)?.async).toBe(false);
    expect(chained(read(DIALOGUE_SESSION), /\bonDone\(\)/)).toEqual([]);
  });

  it("the review screen renders every section in one commit, with no stagger", () => {
    /** What spreads a list over time: a delay, a timer, a frame, a partial or virtualised render. */
    const stagger = (source: string): string[] => {
      const text = code(source);
      const checks: readonly (readonly [string, RegExp])[] = [
        ["delay", /\.\s*delay\s*\(|\bwithDelay\b/],
        ["timer", /\bset(?:Timeout|Interval)\b|\brequestAnimationFrame\b|\brunAfterInteractions\b/],
        ["deferred render", /\buseDeferredValue\b|\bstartTransition\b|\buseTransition\b/],
        ["partial list", /\bsections\s*\.\s*(?:slice|splice)\s*\(/],
        ["virtualised list", /\b(?:FlatList|SectionList|VirtualizedList|FlashList)\b/],
      ];
      return checks.filter(([, re]) => re.test(text)).map(([name]) => name);
    };
    for (const [sample, name] of [
      ["<Animated.View entering={FadeIn.delay(i * 60)} />", "delay"],
      ["o.value = withDelay(i * 60, fade);", "delay"],
      ["const t = setTimeout(() => setShown((n) => n + 1), 60);", "timer"],
      ["const shown = useDeferredValue(sections);", "deferred render"],
      ["{sections.slice(0, shown).map((s) => <Card key={s.id} />)}", "partial list"],
      ["<FlatList data={sections} renderItem={row} />", "virtualised list"],
    ] as const) {
      expect(stagger(sample), sample).toContain(name);
    }
    expect(stagger("{sections.map((section) => <Card key={section.id} />)}")).toEqual([]);

    const review = code(read(REVIEW));
    // Every section is computed in the render, from the note, at once…
    expect(review).toMatch(/const sections = buildNote\(/);
    // …and drawn by one map with no index, which is what a stagger multiplies.
    // (`summary.sections` is the consent summary's list of titles, not the note.)
    const maps = [
      ...review.matchAll(/(?<![.\w])sections\.map\(\s*\(\s*(\w+)\s*(,\s*\w+\s*)?\)\s*=>/g),
    ];
    expect(maps).toHaveLength(1);
    expect(maps[0][2]).toBeUndefined();
    // No section carries an entrance of its own.
    const open = review.indexOf("(", maps[0].index);
    expect(review.slice(open, closing(review, open))).not.toMatch(/\bentering\b/);

    // Nothing the screen renders spreads it out: not the screen, and not a
    // component it draws.
    const drawn = [...review.matchAll(/from "@\/components\/(\w+)"/g)].map(
      (m) => `src/components/${m[1]}.tsx`,
    );
    expect(drawn.length).toBeGreaterThan(3);
    const offenders = [REVIEW, ...drawn].flatMap((name) =>
      stagger(read(name)).map((what) => `${name}: ${what}`),
    );
    expect(offenders).toEqual([]);
  });
});
