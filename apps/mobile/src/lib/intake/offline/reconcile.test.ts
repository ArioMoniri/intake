/**
 * INT-142 — the sync conflict rule, proved as a pure, deterministic function.
 *
 * The rule (documented in reconcile.ts) reconciles the device-local draft with
 * the server copy when connectivity returns. It has ONE property the
 * acceptance rests on: NO SILENT DATA LOSS. Every branch either keeps the
 * local draft, adopts the remote, or — when both diverged — declares a
 * conflict and preserves the loser as a copy. Nothing is ever overwritten
 * without the losing version surviving somewhere.
 */
import { describe, expect, it } from "vitest";

import { emptyNoteState, noteReducer, type NoteState } from "../note";
import { reconcile, type DraftRecord } from "./reconcile";

function note(complaint: string): NoteState {
  return noteReducer(emptyNoteState(), {
    type: "answer",
    questionId: "complaint",
    values: [complaint],
  });
}

function rec(over: Partial<DraftRecord>): DraftRecord {
  return {
    visitId: "v1",
    note: note("base"),
    revision: 0,
    dirty: false,
    updatedAt: 1000,
    origin: "device-a",
    ...over,
  };
}

describe("reconcile — deterministic sync conflict rule", () => {
  it("pushes a local-only draft the server has never seen", () => {
    const local = rec({ revision: 0, dirty: true, updatedAt: 5000 });
    const res = reconcile(local, null);
    expect(res.outcome).toBe("push");
    expect(res.winner).toBe(local);
    expect(res.loser).toBeNull();
  });

  it("adopts a remote draft the device has never seen", () => {
    const remote = rec({ revision: 3 });
    const res = reconcile(null, remote);
    expect(res.outcome).toBe("take-remote");
    expect(res.winner).toBe(remote);
    expect(res.loser).toBeNull();
  });

  it("is in-sync when the local copy is clean and no newer revision exists", () => {
    const local = rec({ revision: 4, dirty: false });
    const remote = rec({ revision: 4 });
    expect(reconcile(local, remote).outcome).toBe("in-sync");
  });

  it("takes the remote when the local copy is clean and the server advanced", () => {
    const local = rec({ revision: 4, dirty: false });
    const remote = rec({ revision: 5, note: note("server-newer") });
    const res = reconcile(local, remote);
    expect(res.outcome).toBe("take-remote");
    expect(res.winner).toBe(remote);
    expect(res.loser).toBeNull();
  });

  it("fast-forward pushes local edits when the server has not moved past our base", () => {
    const local = rec({ revision: 4, dirty: true, updatedAt: 9000, note: note("local-edit") });
    const remote = rec({ revision: 4 });
    const res = reconcile(local, remote);
    expect(res.outcome).toBe("push");
    expect(res.winner).toBe(local);
    expect(res.loser).toBeNull();
  });

  it("declares a conflict when BOTH diverged, and keeps both copies", () => {
    const local = rec({ revision: 4, dirty: true, updatedAt: 9000, note: note("local") });
    const remote = rec({ revision: 6, updatedAt: 8000, note: note("remote") });
    const res = reconcile(local, remote);
    expect(res.outcome).toBe("conflict");
    // last-writer-wins by updatedAt: local (9000) beats remote (8000)
    expect(res.winner).toBe(local);
    expect(res.loser).toBe(remote); // preserved, never dropped
  });

  it("last-writer-wins picks the remote when it is the newer edit", () => {
    const local = rec({ revision: 4, dirty: true, updatedAt: 7000 });
    const remote = rec({ revision: 6, updatedAt: 9500 });
    const res = reconcile(local, remote);
    expect(res.outcome).toBe("conflict");
    expect(res.winner).toBe(remote);
    expect(res.loser).toBe(local);
  });

  it("breaks a timestamp tie deterministically by origin, never at random", () => {
    const local = rec({ revision: 4, dirty: true, updatedAt: 9000, origin: "device-b" });
    const remote = rec({ revision: 6, updatedAt: 9000, origin: "device-a" });
    const first = reconcile(local, remote);
    const second = reconcile(local, remote);
    expect(first.outcome).toBe("conflict");
    expect(first.winner).toBe(second.winner); // stable across calls
    // origin ascending is the tiebreaker: device-a wins over device-b
    expect(first.winner).toBe(remote);
  });

  it("throws rather than inventing a result when both sides are absent", () => {
    expect(() => reconcile(null, null)).toThrow();
  });
});
