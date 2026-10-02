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
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { code } from "../../../e2e/motionSource";
import { sectionLabelKey, sectionPanelModel } from "../dialogue/sectionPanel";
import {
  dialogueStreamReducer,
  initialDialogueStreamState,
  type DialogueStreamAction,
  type DialogueStreamState,
} from "../dialogue/stream";
import { intakeQuestions, packForVisit } from "../intake/questions";
import {
  voiceIntakeReducer,
  type VoiceIntakeAction,
  type VoiceIntakeState,
} from "../intake/voiceFirst";
import { reducedMotion } from "../prefs/appearance";
import { motion } from "../theme";
import {
  WORK,
  dialogueScene,
  fadeOf,
  initialDialogueMotion,
  nodeKey,
  releaseDialogueMotion,
  revealId,
  sameScene,
  stepDialogueMotion,
  typedFallback,
  typedStep,
  type DialogueMotion,
  type DialogueScene,
  type TypedStep,
} from "./transients";

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
    expect(inside(body, at("styles.progressRow"))).toBe(false);
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
/* ------------------------------------------------------------------ */
/* MOTION-8 — dialogue transients wired to the arbiter (INT-337)       */
/* ------------------------------------------------------------------ */

/*
 * docs/design/motion/motion-verification.md §4 MOTION-8; intake-voice-motion-
 * spec.md C1, C3–C10 and §3.3; ADR-033 §2 (Proposed). The dialogue's motion is
 * one pure reducer over "scenes" derived from the conversation state: each new
 * element is a commit to the INT-334 arbiter, and the arbiter's answer is the
 * only thing that decides whether it fades. These tests drive the real
 * dialogue reducer through a whole conversation and read every frame.
 */

const PACK = intakeQuestions;

type Step =
  | DialogueStreamAction
  | { readonly type: "composer"; readonly focused: boolean }
  /** The running fade ended (the device reports it; see useDialogueMotion). */
  | { readonly type: "fade_ended" };

interface Frame {
  readonly state: DialogueStreamState;
  readonly scene: DialogueScene;
  readonly motion: DialogueMotion;
  /** Every element fading in on this frame. */
  readonly fading: readonly string[];
}

/** DialogueIntake's own rule: option chips show on a confirm turn that is not free text. */
function chipsOpenIn(state: DialogueStreamState): boolean {
  const { turn } = state;
  return turn.phase === "confirming" && PACK[turn.step]?.kind !== "text";
}

function sceneOf(state: DialogueStreamState, composerFocused: boolean): DialogueScene {
  const { filled, total } = sectionPanelModel(PACK, state, []);
  return dialogueScene(state, {
    composerFocused,
    chipsOpen: chipsOpenIn(state),
    strip: { filled, total },
  });
}

/** Every element id the dialogue can show: bubbles, their revealed text, the chips, the work ring. */
function idsOf(scene: DialogueScene): string[] {
  return [
    ...scene.entries.flatMap((e) => [e.key, revealId(e.key)]),
    ...(scene.chips === null ? [] : [scene.chips]),
    WORK,
  ];
}

interface Player {
  readonly frame: (step: Step) => Frame;
}

function player(reduce = false): Player {
  let state = initialDialogueStreamState(PACK);
  let focused = false;
  let m = initialDialogueMotion(sceneOf(state, focused));
  return {
    frame(step) {
      if (step.type === "composer") {
        focused = step.focused;
      } else if (step.type === "fade_ended") {
        const id = m.arbiter.running?.id;
        if (id !== undefined) {
          m = releaseDialogueMotion(m, id);
        }
      } else {
        state = dialogueStreamReducer(PACK, state, step);
      }
      const scene = sceneOf(state, focused);
      if (!sameScene(m.scene, scene)) {
        m = stepDialogueMotion(m, scene, { reduce });
      }
      const fading = idsOf(scene).filter((id) => fadeOf(m, id, { reduce }) !== undefined);
      return { state, scene, motion: m, fading };
    },
  };
}

function play(steps: readonly Step[], reduce = false): Frame[] {
  const p = player(reduce);
  return steps.map((step) => p.frame(step));
}

const HEADACHE = { values: ["headache"], quote: "başım ağrıyor" };
const DAYS = { values: ["days"], quote: "iki gündür" };

/** One whole conversation: ask-ahead, a typed answer, two retroactive confirm turns, a re-ask. */
const CONVO: readonly Step[] = [
  { type: "speech_done" }, // 0: listening, complaint
  { type: "utterance", workId: 1 }, // 1: speaking duration; w-1 transcribing; work starts
  { type: "fade_ended" }, // 2
  { type: "speech_done" }, // 3: listening, duration (window shut)
  { type: "transcript_ready", workId: 1, text: "başım ağrıyor" }, // 4: reveal waits
  { type: "utterance", workId: 2 }, // 5: speaking extra; the window opens
  { type: "fade_ended" }, // 6
  { type: "speech_done" }, // 7: listening, extra
  { type: "composer", focused: true }, // 8
  { type: "typed", workId: 3, text: "başka bir şey yok" }, // 9: settling
  { type: "composer", focused: false }, // 10
  { type: "extract_settled", workId: 1, candidates: { complaint: HEADACHE } }, // 11: confirm turn
  { type: "fade_ended" }, // 12
  { type: "transcript_ready", workId: 2, text: "iki gündür" }, // 13: reveal at once
  { type: "fade_ended" }, // 14
  { type: "speech_done" }, // 15: confirming; the chips enter
  { type: "fade_ended" }, // 16
  { type: "confirm", values: ["headache"] }, // 17: settling
  { type: "extract_settled", workId: 2, candidates: { duration: DAYS } }, // 18: confirm turn
  { type: "fade_ended" }, // 19
  { type: "speech_done" }, // 20: confirming
  { type: "confirm", values: ["days"] }, // 21: settling
  { type: "extract_settled", workId: 3, candidates: {} }, // 22: re-ask extra
];

const FRAMES = play(CONVO);

/** The scene key of the newest agent bubble in a frame. */
function newestAgent(frame: Frame): string {
  const agents = frame.scene.entries.filter((e) => e.kind === "agent");
  return agents[agents.length - 1].key;
}

/** Hand-built scenes, for the window rules the reducer reaches only by timing. */
function scene(over: Partial<DialogueScene>): DialogueScene {
  return {
    entries: [{ key: "w-1", kind: "transcribing" }],
    chips: null,
    working: false,
    strip: { filled: 0, total: 3 },
    windowOpen: false,
    ...over,
  };
}

describe("MOTION-8 — content (C1, C4, C5, C7, C8)", () => {
  it("content enters with a 120 ms out-fade, opacity only, delay 0", () => {
    const confirm = FRAMES[11];
    const key = newestAgent(confirm);
    expect(key.startsWith("agent_confirm:")).toBe(true);
    expect(confirm.fading).toEqual([key]);
    expect(fadeOf(confirm.motion, key, { reduce: false })).toEqual(FADE);
    // Under reduce-motion the same conversation shows the same elements, still.
    const still = play(CONVO, true);
    for (const [i, frame] of still.entries()) {
      expect(frame.fading, `frame ${i}`).toEqual([]);
      expect(frame.motion.arbiter.running, `frame ${i}`).toBeNull();
      expect(Object.keys(frame.motion.entered).sort(), `frame ${i}`).toEqual(
        Object.keys(FRAMES[i].motion.entered).sort(),
      );
    }
  });

  it("content is never deferred by the commit window", () => {
    // The composer holds focus while a typed answer brings the next question.
    const focused = play([
      { type: "speech_done" },
      { type: "composer", focused: true },
      { type: "typed", workId: 1, text: "başım ağrıyor" },
    ]);
    const last = focused[2];
    expect(last.scene.windowOpen).toBe(false);
    expect(last.motion.entered[newestAgent(last)]).toBe("animate");
    // Every agent bubble and every chip group is on screen in the frame that adds it.
    for (const [i, frame] of [...FRAMES, ...focused].entries()) {
      for (const e of frame.scene.entries.filter((x) => x.kind === "agent")) {
        expect(frame.motion.entered[e.key], `frame ${i} ${e.key}`).toBeDefined();
      }
      if (frame.scene.chips !== null) {
        expect(frame.motion.entered[frame.scene.chips], `frame ${i}`).toBeDefined();
      }
      expect(frame.motion.arbiter.deferred.filter((c) => c.cls === "content")).toEqual([]);
    }
  });

  it("the patient's own typed message renders instantly", () => {
    const typed = FRAMES[9];
    expect(typed.scene.windowOpen).toBe(false);
    for (const id of ["w-3", revealId("w-3")]) {
      expect(typed.motion.entered[id], id).toBe("instant");
      expect(typed.fading).not.toContain(id);
    }
    expect(typed.motion.arbiter.deferred.map((c) => c.id)).not.toContain(revealId("w-3"));
  });

  it("confirm chips enter as one group; bar actions are instant", () => {
    const chips = FRAMES[15];
    expect(chips.state.turn.phase).toBe("confirming");
    expect(chips.scene.chips).not.toBeNull();
    // One element for the whole group, however many options it holds; the bar's
    // buttons are not elements of the motion layer at all.
    expect(chips.fading).toEqual([chips.scene.chips]);
    expect(PACK[0].options!.length).toBeGreaterThan(1);
    expect(idsOf(chips.scene).filter((id) => id.startsWith("chips:"))).toHaveLength(1);
  });

  it("chip selection is instant in both lanes, and a pre-selected suggestion carries no emphasis motion", () => {
    // The selection is not an input to either lane's motion: the dialogue's
    // scene is the conversation, the composer focus, the chips' presence and
    // the strip; the typed step is keyed by its question alone.
    const chips = FRAMES[15];
    const again = sceneOf(chips.state, false);
    expect(sameScene(chips.scene, again)).toBe(true);
    expect(stepDialogueMotion(chips.motion, again, { reduce: false })).toEqual(chips.motion);
    expect(typedStep("complaint", { reduce: false })).toEqual(
      typedStep("complaint", { reduce: false }),
    );
    // The suggestion arrives inside the one chip group: nothing else of its own moves.
    expect(chips.fading).toHaveLength(1);
  });

  it("confirm commit adds no motion of its own", () => {
    const before = FRAMES[16];
    const after = FRAMES[17];
    expect(after.state.turn.phase).toBe("settling");
    expect(after.scene.chips).toBeNull();
    // The chips leave in the commit that removes them, and nothing fades.
    expect(after.fading).toEqual([]);
    expect(Object.keys(after.motion.entered).filter((k) => k.startsWith("chips:"))).toEqual([]);
    expect(Object.keys(after.motion.entered).length).toBeLessThan(
      Object.keys(before.motion.entered).length,
    );
    // The next element is the next turn's content.
    expect(FRAMES[18].fading).toEqual([newestAgent(FRAMES[18])]);
  });

  it("a section change adds no separate animated element", () => {
    const frame = FRAMES[5];
    const asked = frame.scene.entries.filter((e) => e.kind === "agent").map((e) => e.key);
    const [prevQ, nextQ] = asked
      .slice(-2)
      .map((key) => PACK.find((q) => key.includes(`:${q.id}:`))!);
    expect(sectionLabelKey(prevQ)).not.toBe(sectionLabelKey(nextQ));
    const added = frame.scene.entries.filter((e) =>
      FRAMES[4].scene.entries.every((p) => p.key !== e.key),
    );
    expect(added.map((e) => e.kind).sort()).toEqual(["agent", "transcribing"]);
    expect(frame.fading.length).toBeLessThanOrEqual(1);
  });
});

describe("MOTION-8 — commit-window classes (C3, C9, C10)", () => {
  it("transcript reveal is rail-class: deferred while listening or composing, flushed at the next window", () => {
    // Listening: the words wait, and the bubble keeps its transcribing line.
    const waiting = FRAMES[4];
    expect(waiting.state.turn.phase).toBe("listening");
    expect(waiting.motion.entered[revealId("w-1")]).toBeUndefined();
    expect(waiting.motion.arbiter.deferred).toContainEqual(
      expect.objectContaining({ cls: "railCommit", id: revealId("w-1") }),
    );
    // The next window applies it, never drops it.
    expect(FRAMES[5].motion.entered[revealId("w-1")]).toBeDefined();
    expect(FRAMES[5].fading).toEqual([revealId("w-1")]);
    // Composing shuts the window too, on an agent turn.
    const composing = play([
      { type: "speech_done" },
      { type: "utterance", workId: 1 },
      { type: "composer", focused: true },
      { type: "transcript_ready", workId: 1, text: "başım ağrıyor" },
      { type: "composer", focused: false },
    ]);
    expect(composing[3].state.turn.phase).toBe("speaking");
    expect(composing[3].motion.entered[revealId("w-1")]).toBeUndefined();
    expect(composing[4].motion.entered[revealId("w-1")]).toBeDefined();
    // With the window open, it is applied at once.
    expect(FRAMES[13].motion.entered[revealId("w-2")]).toBeDefined();
  });

  it("transcript reveal animates the new text only, never the bubble frame", () => {
    for (const i of [5, 13]) {
      const frame = FRAMES[i];
      const [id] = frame.fading;
      expect(id.endsWith(":text"), `frame ${i}`).toBe(true);
      const bubble = id.slice(0, -":text".length);
      expect(frame.fading).not.toContain(bubble);
      // The bubble entered instantly at the microphone and keeps its node.
      expect(frame.motion.entered[bubble]).toBe("instant");
      expect(nodeKey(frame.motion, bubble)).toBe(nodeKey(FRAMES[i - 1].motion, bubble));
    }
  });

  it("progress numerals are never tweened; the strip count is rail-class", () => {
    const frames = play([
      { type: "speech_done" },
      { type: "utterance", workId: 1 },
      { type: "speech_done" }, // listening
      {
        type: "extract_settled",
        workId: 1,
        candidates: { complaint: HEADACHE },
      },
      { type: "confirm_pending", questionId: "complaint" }, // a panel-row confirm while listening
      { type: "utterance", workId: 2 }, // the next window
    ]);
    const shut = frames[4];
    expect(shut.scene.windowOpen).toBe(false);
    expect(shut.scene.strip.filled).toBe(1);
    expect(shut.motion.strip.filled).toBe(0);
    expect(frames[5].motion.strip).toEqual(frames[5].scene.strip);
    // Only true counts are ever shown, and the strip is never an animated element.
    const seen = frames.map((f) => JSON.stringify(f.scene.strip));
    for (const f of frames) {
      expect(seen).toContain(JSON.stringify(f.motion.strip));
      expect(f.fading.filter((id) => id.includes("strip"))).toEqual([]);
    }
  });

  it("work chips outrank rail commits and wait for the window", () => {
    // The work indicator and a transcript both land while the patient talks…
    let m = initialDialogueMotion(scene({}));
    m = stepDialogueMotion(
      m,
      scene({ entries: [{ key: "w-1", kind: "patient" }], working: true }),
      { reduce: false },
    );
    expect(m.ring).toBe(false);
    expect(m.arbiter.deferred.map((c) => c.cls).sort()).toEqual(["railCommit", "workChip"]);
    // …and at the window the work chip animates, the reveal renders instantly.
    m = stepDialogueMotion(
      m,
      scene({
        entries: [{ key: "w-1", kind: "patient" }],
        working: true,
        windowOpen: true,
      }),
      { reduce: false },
    );
    expect(m.ring).toBe(true);
    expect(m.arbiter.running?.id).toBe(WORK);
    expect(m.entered[revealId("w-1")]).toBe("instant");
  });

  it("a work indicator withdrawn before the window is never rendered, and leaves at once", () => {
    let m = initialDialogueMotion(scene({}));
    m = stepDialogueMotion(m, scene({ working: true }), { reduce: false });
    m = stepDialogueMotion(m, scene({ working: false }), { reduce: false });
    m = stepDialogueMotion(m, scene({ working: false, windowOpen: true }), {
      reduce: false,
    });
    expect(m.ring).toBe(false);
    expect(m.arbiter.deferred).toEqual([]);
    // Shown, then finished: it goes at the next window, with no fade out.
    m = stepDialogueMotion(m, scene({ working: true, windowOpen: true }), {
      reduce: false,
    });
    expect(m.ring).toBe(true);
    m = stepDialogueMotion(m, scene({ working: false, windowOpen: false }), {
      reduce: false,
    });
    expect(m.ring).toBe(true);
    m = stepDialogueMotion(m, scene({ working: false, windowOpen: true }), {
      reduce: false,
    });
    expect(m.ring).toBe(false);
    expect(fadeOf(m, WORK, { reduce: false })).toBeUndefined();
  });
});

describe("MOTION-8 — one element at a time, nothing waits on motion", () => {
  it("no frame shows two questions, and nothing fades out", () => {
    for (const [i, frame] of FRAMES.entries()) {
      expect(frame.fading.length, `frame ${i}`).toBeLessThanOrEqual(1);
      const keys = frame.scene.entries.map((e) => e.key);
      expect(new Set(keys).size, `frame ${i}`).toBe(keys.length);
      // A removed element has no fade: every fading id is on screen now.
      for (const id of frame.fading) {
        expect(idsOf(frame.scene)).toContain(id);
      }
    }
    // The re-ask brings its line and the question together, as one turn.
    const reask = FRAMES[22];
    const kinds = reask.scene.entries.slice(-2).map((e) => e.key.split(":")[0]);
    expect(kinds).toEqual(["agent_unclear", "agent_question"]);
    expect(reask.fading.length).toBeLessThanOrEqual(1);
  });

  describe("on a fake clock", () => {
    beforeEach(() => {
      vi.useFakeTimers();
      vi.setSystemTime(0);
    });
    afterEach(() => {
      vi.useRealTimers();
    });

    it("a fade stalled 30 s never defers content or delays a turn", () => {
      // The same conversation with every fade end lost: the device never
      // reports one, and 30 s pass before every event.
      const steps = CONVO.filter((s) => s.type !== "fade_ended");
      const live = play(CONVO).filter((_, i) => CONVO[i].type !== "fade_ended");
      const stalled = player();
      for (const [i, step] of steps.entries()) {
        vi.advanceTimersByTime(30_000);
        const at = Date.now();
        const frame = stalled.frame(step);
        expect(Date.now() - at).toBe(0);
        // The turn is the reducer's alone, and every new bubble is on screen.
        expect(frame.state.turn, `step ${i}`).toEqual(live[i].state.turn);
        expect(frame.scene.entries).toEqual(live[i].scene.entries);
        for (const e of frame.scene.entries.filter((x) => x.kind === "agent")) {
          expect(frame.motion.entered[e.key], `step ${i} ${e.key}`).toBeDefined();
        }
        // Nothing ever fades beside the stuck element.
        expect(frame.fading.length).toBeLessThanOrEqual(1);
      }
      expect(vi.getTimerCount()).toBe(0);
      expect(Date.now()).toBe(steps.length * 30_000);
    });
  });
});
