/**
 * Typed-lane motion (INT-339, MOTION-10;
 * docs/design/motion/motion-verification.md §4 MOTION-10, and C15 and C16 of
 * intake-voice-motion-spec.md).
 *
 * Pure — no React Native or Reanimated import — so the plans are
 * node-testable. The typed intake screen hands each plan's `enter` to the
 * Reanimated adapter (native/reanimated.ts) and writes no number of its own.
 *
 * Both surfaces are enter-only, and the shape is the one fade (fade.ts):
 * - `typedFallback`: the typed steps' container, when it replaces the voice
 *   lane (failure, hand-over, or "Yazarak devam edin"). The dialogue unmounts
 *   at 0 ms and the steps fade in over `motion.duration.fade`, so the switch
 *   is fully visible 120 ms after its commit, inside INT-135's 2 s at every
 *   setting;
 * - `typedStep`: one question's body. It is keyed by the question, so a step
 *   change removes the old body in the commit that mounts the next one, and
 *   only the next one fades in. No frame holds two questions. The progress
 *   row and the glass-bar CTA sit outside it and swap instantly (C9, C16).
 *
 * There is no exit: `exitMs` is the literal 0 (motion-verification.md §2.1
 * #3). A fading exit is a second animated element whenever something replaces
 * it, and it is the only thing that could keep a removed question on screen.
 * Under reduce-motion `enter` is undefined and the content is simply there.
 */
import type { DialogueStreamState, StreamEntry } from "../dialogue/stream";
import { motion } from "../theme";
import {
  EMPTY_ARBITER,
  arbitrate,
  flush,
  invalidate,
  release,
  windowOpen,
  type ArbiterState,
  type Commit,
  type Render,
} from "./arbiter";
import { enterFor, type FadeContext, type FadeSpec } from "./fade";

/** A mount that may fade in and never fades out. */
export interface EnterOnly {
  /** A layout animation's entrance, or none: under reduce-motion there is nothing to register. */
  readonly enter: FadeSpec | undefined;
  /** The leaving element is gone in the commit that removes it. */
  readonly exitMs: typeof motion.duration.instant;
}

/** One typed question's body. */
export interface TypedStep extends EnterOnly {
  /** The React key: a new question is a new element, the same question the same one. */
  readonly key: string;
}

function enterOnly(context: FadeContext): EnterOnly {
  return { enter: enterFor(context), exitMs: motion.duration.instant };
}

/** The typed steps' container, entering in place of the voice lane (C15). */
export function typedFallback(context: FadeContext): EnterOnly {
  return enterOnly(context);
}

/** A question's body in the typed steps (C16). */
export function typedStep(questionId: string, context: FadeContext): TypedStep {
  return { key: questionId, ...enterOnly(context) };
}
/* ------------------------------------------------------------------ */
/* INT-337 (MOTION-8): the dialogue's transients, through the arbiter  */
/* ------------------------------------------------------------------ */

/*
 * docs/design/motion/motion-verification.md §4 MOTION-8; intake-voice-motion-
 * spec.md C1, C3–C10 and §3.3. The dialogue describes what it shows as a
 * `DialogueScene`, derived from the conversation state; `stepDialogueMotion`
 * diffs two scenes and asks the arbiter (./arbiter.ts) about every element
 * that is new. Its answer is the only thing that decides whether an element
 * fades, renders instantly or waits for the commit window:
 *
 * - content (C1, C5, C8): a new agent bubble, or the confirm turn's chip
 *   group as ONE element. It is never deferred. A section change is the next
 *   question's bubble and adds nothing of its own;
 * - the patient's own words (C4): a typed message, and the bubble opened at
 *   the microphone, are there at once, outside the arbiter;
 * - a transcript reveal (C3) is a rail commit. The words wait while the
 *   patient is listening or composing, the bubble keeps its transcribing
 *   line, and only the new text node fades, never the bubble frame;
 * - the work indicator (C10; drawn as the orb's ring, the dialogue's one work
 *   chip) is a work-chip commit: it waits for the window and outranks a rail
 *   commit. It leaves instantly, at the next window;
 * - the strip's count (C9) waits for the window like a rail commit and swaps
 *   instantly, so it never takes the animation slot and never shows a number
 *   that was not true;
 * - chip selection and the confirm tap are not inputs here at all, so they
 *   add no motion (C6, C7). Exits are instant: a removed element is gone in
 *   the commit that removes it.
 *
 * Nothing reads a clock. The end of a fade is reported by the device
 * (native/useDialogueMotion.ts) through `releaseDialogueMotion`; a report
 * that never comes holds the slot, so later content renders instantly
 * instead of fading, and is never deferred or delayed.
 */

/** The work indicator's element id. */
export const WORK = "work";

export type SceneKind = "agent" | "patient" | "transcribing";

export interface SceneEntry {
  /** Stable across removals elsewhere in the stream. */
  readonly key: string;
  readonly kind: SceneKind;
}

export interface Strip {
  readonly filled: number;
  readonly total: number;
}

export interface DialogueScene {
  /** One per stream entry, in stream order. */
  readonly entries: readonly SceneEntry[];
  /** The confirm turn's chip group, or null when no chips show. */
  readonly chips: string | null;
  /** Transcription or extraction is in flight behind the turn. */
  readonly working: boolean;
  readonly strip: Strip;
  /** The arbiter's commit window: not listening, composer not focused. */
  readonly windowOpen: boolean;
}

export interface SceneInputs {
  readonly composerFocused: boolean;
  /** Option chips show for the live confirm turn. */
  readonly chipsOpen: boolean;
  readonly strip: Strip;
}

/** A stream entry's key: its work id, or its kind, question and occurrence. */
function sceneKey(stream: readonly StreamEntry[], index: number): string {
  const entry = stream[index];
  if (entry.kind === "patient") {
    return `w-${entry.workId}`;
  }
  const earlier = stream
    .slice(0, index)
    .filter((e) => e.kind === entry.kind && e.questionId === entry.questionId).length;
  return `${entry.kind}:${entry.questionId}:${earlier}`;
}

/** The id of a patient bubble's revealed text. */
export function revealId(key: string): string {
  return `${key}:text`;
}

function kindOf(entry: StreamEntry): SceneKind {
  if (entry.kind !== "patient") {
    return "agent";
  }
  return entry.status === "transcribing" ? "transcribing" : "patient";
}

/** What the dialogue shows, as far as motion is concerned. */
export function dialogueScene(state: DialogueStreamState, inputs: SceneInputs): DialogueScene {
  const entries = state.stream.map((entry, index) => ({
    key: sceneKey(state.stream, index),
    kind: kindOf(entry),
  }));
  const confirms = entries.filter((e) => e.key.startsWith("agent_confirm:"));
  const lastConfirm = confirms[confirms.length - 1];
  return {
    entries,
    chips: inputs.chipsOpen && lastConfirm !== undefined ? `chips:${lastConfirm.key}` : null,
    working: state.inflight.length > 0 || entries.some((e) => e.kind === "transcribing"),
    strip: inputs.strip,
    windowOpen: windowOpen({
      turnPhase: state.turn.phase,
      composerFocused: inputs.composerFocused,
    }),
  };
}

/** Whether two scenes would render the same motion. */
export function sameScene(a: DialogueScene, b: DialogueScene): boolean {
  return (
    a.chips === b.chips &&
    a.working === b.working &&
    a.windowOpen === b.windowOpen &&
    a.strip.filled === b.strip.filled &&
    a.strip.total === b.strip.total &&
    a.entries.length === b.entries.length &&
    a.entries.every((e, i) => e.key === b.entries[i].key && e.kind === b.entries[i].kind)
  );
}

type Shown = Exclude<Render, "deferred">;

export interface DialogueMotion {
  readonly scene: DialogueScene;
  readonly arbiter: ArbiterState;
  /** Every element on screen, and how it arrived. Absent: not shown yet. */
  readonly entered: Readonly<Record<string, Shown>>;
  /** Elements snapped to their end state mid-fade: their node is remounted still. */
  readonly snapped: readonly string[];
  /** The work indicator is shown. */
  readonly ring: boolean;
  /** The strip's count as shown. */
  readonly strip: Strip;
}

/** The dialogue's first frame: everything is simply there (skipEntering). */
export function initialDialogueMotion(scene: DialogueScene): DialogueMotion {
  const entered: Record<string, Shown> = {};
  for (const e of scene.entries) {
    entered[e.key] = "instant";
    if (e.kind === "patient") {
      entered[revealId(e.key)] = "instant";
    }
  }
  if (scene.chips !== null) {
    entered[scene.chips] = "instant";
  }
  return {
    scene,
    arbiter: EMPTY_ARBITER,
    entered,
    snapped: [],
    ring: scene.working,
    strip: scene.strip,
  };
}

/** One scene change, decided now. */
export function stepDialogueMotion(
  prev: DialogueMotion,
  next: DialogueScene,
  { reduce }: FadeContext,
): DialogueMotion {
  if (sameScene(prev.scene, next)) {
    return prev;
  }
  const win = { open: next.windowOpen };
  let arbiter = prev.arbiter;
  const entered: Record<string, Shown> = { ...prev.entered };
  const snapped = new Set(prev.snapped);
  let ring = prev.ring;

  const take = (id: string, render: Shown, snap: string | null) => {
    if (snap !== null) {
      snapped.add(snap);
    }
    if (id === WORK) {
      ring = true;
    } else {
      entered[id] = render;
    }
    if (reduce && render === "animate") {
      // Nothing moves: the slot is free in the same commit.
      arbiter = release(arbiter, id);
    }
  };
  const commit = (c: Commit) => {
    const d = arbitrate(arbiter, c, win);
    arbiter = d.state;
    if (d.render !== "deferred") {
      take(c.id, d.render, d.snapped);
    }
  };
  const gone = (id: string) => {
    arbiter = release(invalidate(arbiter, id), id);
    delete entered[id];
  };

  // 1. Exits are instant; a deferred reveal of a dropped line is never shown.
  const before = new Map(prev.scene.entries.map((e) => [e.key, e.kind]));
  const now = new Set(next.entries.map((e) => e.key));
  for (const e of prev.scene.entries) {
    if (!now.has(e.key)) {
      gone(e.key);
      gone(revealId(e.key));
    }
  }
  if (prev.scene.chips !== null && prev.scene.chips !== next.chips) {
    gone(prev.scene.chips);
  }
  if (prev.scene.working && !next.working) {
    arbiter = invalidate(arbiter, WORK);
  }
  // 2. Earlier deferred commits, at a window, in priority order.
  const flushed = flush(arbiter, win);
  arbiter = flushed.state;
  for (const a of flushed.applied) {
    take(a.commit.id, a.render, a.snapped);
  }
  // 3. This change's window-class commits: the work chip, then the reveals.
  if (next.working && !prev.scene.working && !ring) {
    commit({ cls: "workChip", id: WORK, slot: WORK });
  }
  for (const e of next.entries) {
    if (before.get(e.key) === "transcribing" && e.kind === "patient") {
      commit({ cls: "railCommit", id: revealId(e.key), slot: e.key });
    }
  }
  // 4. Content, never deferred; the patient's own bubbles, at once.
  for (const e of next.entries) {
    if (before.has(e.key)) {
      continue;
    }
    if (e.kind === "agent") {
      commit({ cls: "content", id: e.key });
    } else {
      entered[e.key] = "instant";
      if (e.kind === "patient") {
        entered[revealId(e.key)] = "instant";
      }
    }
  }
  if (next.chips !== null && next.chips !== prev.scene.chips) {
    commit({ cls: "content", id: next.chips });
  }
  // 5. At a window: a finished work indicator leaves, and the strip shows its true count.
  if (win.open && !next.working && ring) {
    ring = false;
    arbiter = release(arbiter, WORK);
  }
  return {
    scene: next,
    arbiter,
    entered,
    snapped: [...snapped],
    ring,
    strip: win.open ? next.strip : prev.strip,
  };
}

/** The device reports that the fade of `id` ended. */
export function releaseDialogueMotion(m: DialogueMotion, id: string): DialogueMotion {
  const arbiter = release(m.arbiter, id);
  return arbiter === m.arbiter ? m : { ...m, arbiter };
}

/** The fade an element enters with now: the arbiter's running element only, never under reduce-motion. */
export function fadeOf(m: DialogueMotion, id: string, context: FadeContext): FadeSpec | undefined {
  return m.arbiter.running?.id === id ? enterFor(context) : undefined;
}

/** An element's React key: a snapped element is remounted at its end state. */
export function nodeKey(m: DialogueMotion, id: string): string {
  return m.snapped.includes(id) ? `${id}~still` : id;
}
