/**
 * The arbiter and the commit window (INT-334, MOTION-5;
 * docs/design/motion/motion-verification.md §4 MOTION-5 and §2.1 #5–#7, #20;
 * intake-voice-motion-spec.md §3.3 ARB-1…ARB-5; files/02 §5.2a rules 1 and 8).
 *
 * The rules, in the spec's words:
 * - one app-authored animation at any instant;
 * - snap, never queue: a strictly higher-priority arrival snaps the running
 *   element to its end state and then animates; an equal or lower one renders
 *   instantly;
 * - hold, never rest: every class but RED only holds the ambient loop; only
 *   RED stops it;
 * - the rail, work-chip and YELLOW commits wait while the patient is
 *   listening or the composer has focus, and are applied at the next window,
 *   never dropped; an invalidated slot is never rendered;
 * - RED bypasses every window and snaps everything.
 *
 * The property test drives thousands of seeded sequences through the reducer.
 * The seed is a constant, so a failure replays exactly; nothing reads a clock.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import {
  ARBITER_ORDER,
  EMPTY_ARBITER,
  arbitrate,
  flush,
  invalidate,
  release,
  waitsForWindow,
  windowOpen,
  type ArbiterState,
  type Commit,
  type CommitClass,
} from "./arbiter";

const OPEN = { open: true } as const;
const SHUT = { open: false } as const;

function commit(cls: CommitClass, id: string, slot?: string): Commit {
  return slot === undefined ? { cls, id } : { cls, id, slot };
}

/** A state with one element already animating. */
function running(cls: CommitClass, id = `${cls}-1`): ArbiterState {
  const d = arbitrate(EMPTY_ARBITER, commit(cls, id), OPEN);
  expect(d.render).toBe("animate");
  return d.state;
}

const ARRIVING = ARBITER_ORDER.filter((c): c is CommitClass => c !== "ambient");
const WINDOWED: readonly CommitClass[] = ["yellowPill", "workChip", "railCommit"];

describe("arbiter (MOTION-5)", () => {
  it("the order is the named tuple, with no priority numbers", () => {
    expect(ARBITER_ORDER).toEqual([
      "red",
      "yellowPill",
      "workChip",
      "railCommit",
      "content",
      "ambient",
    ]);
  });

  it("grants one animated element at a time", () => {
    let state = EMPTY_ARBITER;
    const animated: string[] = [];
    // Every class, lowest priority first, so each one outranks the last.
    for (const cls of [...ARRIVING].reverse().filter((c) => c !== "red")) {
      const d = arbitrate(state, commit(cls, cls), OPEN);
      if (d.render === "animate") {
        animated.push(cls);
      }
      state = d.state;
      // Whatever happened, at most one element is animating now.
      expect(state.running === null || typeof state.running.id === "string").toBe(true);
    }
    // Each higher arrival took the one animation slot from the one before.
    expect(animated).toEqual(["content", "railCommit", "workChip", "yellowPill"]);
    expect(state.running).toEqual({ cls: "yellowPill", id: "yellowPill" });
  });

  it("a lower- or equal-priority arrival renders instantly, never queued", () => {
    for (const [i, first] of ARRIVING.entries()) {
      if (first === "red") {
        continue; // RED never runs: it has no motion to run
      }
      for (const later of ARRIVING.slice(i).filter((c) => c !== "red")) {
        const state = running(first);
        const d = arbitrate(state, commit(later, `${later}-2`), OPEN);
        expect(d.render, `${later} after ${first}`).toBe("instant");
        expect(d.snapped, `${later} after ${first}`).toBeNull();
        // The running element is untouched and nothing waits behind it.
        expect(d.state.running).toEqual(state.running);
        expect(d.state.deferred).toEqual([]);
      }
    }
  });

  it("a higher-priority arrival snaps the running element to its end state first", () => {
    const state = running("content", "question-4");
    const d = arbitrate(state, commit("workChip", "chip-1"), OPEN);
    expect(d.snapped).toBe("question-4");
    expect(d.render).toBe("animate");
    expect(d.state.running).toEqual({ cls: "workChip", id: "chip-1" });
    // Near miss: equal priority does not snap.
    const same = arbitrate(state, commit("content", "question-5"), OPEN);
    expect(same.snapped).toBeNull();
    expect(same.render).toBe("instant");
  });

  it("RED snaps every running element, stops the ambient loop and bypasses every window", () => {
    for (const cls of ARRIVING.filter((c) => c !== "red")) {
      for (const window of [OPEN, SHUT]) {
        const state = running(cls);
        expect(state.ambient).toBe("held");
        const d = arbitrate(state, commit("red", "red-1"), window);
        expect(d.render, `${cls} ${window.open}`).toBe("instant");
        expect(d.snapped).toBe(`${cls}-1`);
        expect(d.state.running).toBeNull();
        expect(d.state.ambient).toBe("stopped");
        expect(d.state.deferred).toEqual([]);
      }
    }
    // With nothing running and the window shut, RED still renders at once.
    const idle = arbitrate(EMPTY_ARBITER, commit("red", "red-1"), SHUT);
    expect(idle.render).toBe("instant");
    expect(idle.state.ambient).toBe("stopped");
    // Deferred commits are not dropped by a RED: they stay for their window.
    const waiting = arbitrate(EMPTY_ARBITER, commit("railCommit", "rail-1"), SHUT).state;
    expect(arbitrate(waiting, commit("red", "red-1"), SHUT).state.deferred).toEqual([
      commit("railCommit", "rail-1"),
    ]);
  });

  it("only RED stops the ambient loop; every other class holds it at its current value", () => {
    expect(EMPTY_ARBITER.ambient).toBe("running");
    for (const cls of ARRIVING.filter((c) => c !== "red")) {
      const state = running(cls);
      expect(state.ambient, cls).toBe("held");
      // Hold, never rest: the loop resumes when the transient ends.
      expect(release(state, `${cls}-1`).ambient, cls).toBe("running");
    }
    // A stopped loop stays stopped: no later release or commit restarts it.
    let stopped = arbitrate(EMPTY_ARBITER, commit("red", "red-1"), OPEN).state;
    stopped = arbitrate(stopped, commit("content", "question-9"), OPEN).state;
    expect(stopped.ambient).toBe("stopped");
    expect(release(stopped, "question-9").ambient).toBe("stopped");
  });

  it("rail, work-chip and YELLOW commits wait for the window; content never does", () => {
    for (const cls of WINDOWED) {
      expect(waitsForWindow(cls), cls).toBe(true);
      const d = arbitrate(EMPTY_ARBITER, commit(cls, `${cls}-1`), SHUT);
      expect(d.render, cls).toBe("deferred");
      expect(d.state.running).toBeNull();
      expect(d.state.deferred).toEqual([commit(cls, `${cls}-1`)]);
    }
    for (const cls of ["red", "content"] as const) {
      expect(waitsForWindow(cls), cls).toBe(false);
      expect(arbitrate(EMPTY_ARBITER, commit(cls, "x"), SHUT).render, cls).not.toBe("deferred");
    }
  });

  it("the window is closed while listening or while the composer has focus", () => {
    expect(windowOpen({ turnPhase: "listening", composerFocused: false })).toBe(false);
    expect(windowOpen({ turnPhase: "confirming", composerFocused: true })).toBe(false);
    expect(windowOpen({ turnPhase: "speaking", composerFocused: false })).toBe(true);
    expect(windowOpen({ turnPhase: "confirming", composerFocused: false })).toBe(true);
    expect(windowOpen({ turnPhase: "settling", composerFocused: false })).toBe(true);
    // A draft that is not being edited does not hold the window shut (ARB-3
    // revised): an abandoned draft would otherwise hold YELLOW back forever.
    expect(windowOpen({ turnPhase: "done", composerFocused: false })).toBe(true);
  });

  it("a deferred commit is applied at the next window, never dropped", () => {
    let state = EMPTY_ARBITER;
    for (const c of [
      commit("railCommit", "rail-1"),
      commit("yellowPill", "yellow-1"),
      commit("workChip", "chip-1"),
    ]) {
      state = arbitrate(state, c, SHUT).state;
    }
    // Still shut: nothing is applied and nothing is lost.
    const stillShut = flush(state, SHUT);
    expect(stillShut.applied).toEqual([]);
    expect(stillShut.state.deferred).toHaveLength(3);

    const opened = flush(state, OPEN);
    // In priority order: one animates, the rest render instantly.
    expect(opened.applied).toEqual([
      { commit: commit("yellowPill", "yellow-1"), render: "animate", snapped: null },
      { commit: commit("workChip", "chip-1"), render: "instant", snapped: null },
      { commit: commit("railCommit", "rail-1"), render: "instant", snapped: null },
    ]);
    expect(opened.state.deferred).toEqual([]);
    expect(opened.state.running).toEqual({ cls: "yellowPill", id: "yellow-1" });
  });

  it("an invalidated slot is never rendered", () => {
    let state = arbitrate(
      EMPTY_ARBITER,
      commit("railCommit", "rail-1", "transcript-3"),
      SHUT,
    ).state;
    state = arbitrate(state, commit("workChip", "chip-1", "chip-3"), SHUT).state;
    state = invalidate(state, "transcript-3");
    const opened = flush(state, OPEN);
    expect(opened.applied.map((a) => a.commit.id)).toEqual(["chip-1"]);
    // Invalidating an unknown slot changes nothing.
    expect(invalidate(state, "no-such-slot")).toEqual(state);
  });

  it("a re-sent commit replaces its deferred copy instead of stacking", () => {
    let state = arbitrate(EMPTY_ARBITER, commit("workChip", "chip-1"), SHUT).state;
    state = arbitrate(state, commit("railCommit", "rail-1"), SHUT).state;
    state = arbitrate(state, commit("workChip", "chip-1"), SHUT).state;
    expect(state.deferred.map((c) => c.id)).toEqual(["chip-1", "rail-1"]);
  });

  it("YELLOW never pre-empts and never loops", () => {
    // It waits for the window like every commit-window class: it never
    // interrupts the patient mid-sentence ("preempt" belongs to RED alone).
    expect(arbitrate(EMPTY_ARBITER, commit("yellowPill", "y"), SHUT).render).toBe("deferred");
    // It does not stop the ambient loop, and releasing it resumes the loop.
    const state = running("yellowPill", "y");
    expect(state.ambient).toBe("held");
    expect(release(state, "y")).toEqual({ ...EMPTY_ARBITER });
    // Nothing in the arbiter repeats: there is no loop field on a decision.
    const d = arbitrate(EMPTY_ARBITER, commit("yellowPill", "y"), OPEN);
    expect(Object.keys(d).sort()).toEqual(["render", "snapped", "state"]);
  });

  it("a stale release is ignored", () => {
    const state = running("content", "question-1");
    const snapped = arbitrate(state, commit("workChip", "chip-1"), OPEN).state;
    // The snapped element's end event arrives late: the chip keeps its slot.
    expect(release(snapped, "question-1")).toEqual(snapped);
    expect(release(snapped, "chip-1").running).toBeNull();
  });

  it("holds its invariants over seeded random sequences", () => {
    // A small linear congruential generator: the same seed, the same run.
    let seed = 0x2f6b;
    const next = (n: number) => {
      seed = (seed * 1103515245 + 12345) & 0x7fffffff;
      return seed % n;
    };
    const invalidated = new Set<string>();
    const applied = new Map<string, number>();
    let state = EMPTY_ARBITER;
    let windowIsOpen = true;
    for (let step = 0; step < 5000; step += 1) {
      const roll = next(10);
      if (roll < 6) {
        const cls = ARRIVING[next(ARRIVING.length)];
        if (cls === "red" && next(20) !== 0) {
          continue; // RED is rare; when it comes it must dominate
        }
        const id = `${cls}-${step}`;
        const d = arbitrate(state, commit(cls, id, `slot-${next(5)}`), { open: windowIsOpen });
        if (d.render !== "deferred") {
          applied.set(id, (applied.get(id) ?? 0) + 1);
        }
        if (cls === "red") {
          expect(d.render).toBe("instant");
          expect(d.state.ambient).toBe("stopped");
        }
        if (d.render === "deferred") {
          expect(windowIsOpen).toBe(false);
          expect(waitsForWindow(cls)).toBe(true);
        }
        state = d.state;
      } else if (roll < 7 && state.running !== null) {
        state = release(state, state.running.id);
      } else if (roll < 8) {
        const slot = `slot-${next(5)}`;
        for (const c of state.deferred.filter((d) => d.slot === slot)) {
          invalidated.add(c.id);
        }
        state = invalidate(state, slot);
      } else {
        windowIsOpen = !windowIsOpen;
        if (windowIsOpen) {
          const f = flush(state, OPEN);
          const animating = f.applied.filter((a) => a.render === "animate");
          expect(animating.length).toBeLessThanOrEqual(1);
          for (const a of f.applied) {
            expect(invalidated.has(a.commit.id)).toBe(false);
            applied.set(a.commit.id, (applied.get(a.commit.id) ?? 0) + 1);
          }
          state = f.state;
          expect(state.deferred).toEqual([]);
        }
      }
      // One animation at any instant, and the loop is never free while one runs.
      if (state.running !== null) {
        expect(state.ambient).not.toBe("running");
        expect(state.running.cls).not.toBe("red");
      }
      // Nothing is waiting while the window is open.
      if (windowIsOpen) {
        expect(state.deferred).toEqual([]);
      }
    }
    // Every commit that rendered, rendered once.
    for (const [id, count] of applied) {
      expect(count, id).toBe(1);
    }
    expect(applied.size).toBeGreaterThan(1000);
  });

  it("arbitration reads no clock", () => {
    const source = readFileSync(join(__dirname, "arbiter.ts"), "utf8");
    const code = source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
    expect(code).not.toMatch(
      /\bDate\b|\bperformance\b|\bsetTimeout\b|\bsetInterval\b|\brequestAnimationFrame\b|\bMath\.random\b/,
    );
    // Pure: it imports types only, and nothing from React Native or Reanimated.
    const imports = [...code.matchAll(/^import\s+(type\s+)?[^;]*?from\s+["']([^"']+)["']/gm)];
    expect(imports.every((m) => Boolean(m[1]))).toBe(true);
    // The same inputs give the same decision.
    const a = arbitrate(running("content"), commit("workChip", "chip-1"), OPEN);
    const b = arbitrate(running("content"), commit("workChip", "chip-1"), OPEN);
    expect(a).toEqual(b);
  });
});
