/**
 * INT-397 — the notification store tells a save in flight from a save that
 * failed (WCAG 2.2 SC 4.1.3).
 *
 * INT-141's store had one flag, `pending`, set before every save and kept when
 * the server did not confirm. The screen's "not saved yet" line therefore
 * meant both "on its way" and "did not land", and announcing it would have
 * said "Hata" on every toggle (INT-362 left it out for that reason). The typed
 * `save` state separates the two; only `failed` is announced.
 *
 * Saving itself is unchanged: the switch moves at once, and a refused change
 * stays shown rather than snapping back.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { DEFAULT_PREFS, type NotificationPrefs } from "./preferences";
import {
  loadNotificationPrefs,
  prefsSnapshot,
  resetNotificationPrefs,
  saveNotificationPrefs,
  subscribeToPrefs,
  type SaveState,
} from "./store";

const mocks = vi.hoisted(() => ({ authedFetch: vi.fn() }));

vi.mock("@/lib/auth/api", () => ({ authedFetch: mocks.authedFetch }));

const OPTED_OUT: NotificationPrefs = { optedOut: true, quietStart: null, quietEnd: null };
const WIRE_OPTED_OUT = { opted_out: true, quiet_start: null, quiet_end: null };

function ok(body: unknown): Response {
  return { ok: true, status: 200, json: async () => body } as unknown as Response;
}

function refused(status: number): Response {
  return { ok: false, status, json: async () => ({}) } as unknown as Response;
}

/** A server answer the test releases when it chooses. */
function held(): { promise: Promise<Response>; answer: (r: Response) => void } {
  let answer: (r: Response) => void = () => undefined;
  const promise = new Promise<Response>((resolve) => {
    answer = resolve;
  });
  return { promise, answer };
}

/** Every `save` state the screen is shown, in order, without repeats. */
function watchSave(): { seen: SaveState[]; stop: () => void } {
  const seen: SaveState[] = [];
  const stop = subscribeToPrefs(() => {
    const now = prefsSnapshot().save;
    if (seen[seen.length - 1] !== now) {
      seen.push(now);
    }
  });
  return { seen, stop };
}

afterEach(() => {
  resetNotificationPrefs();
  mocks.authedFetch.mockReset();
});

describe("a save in flight is not a failed save (INT-397)", () => {
  it("a fresh working copy is idle", () => {
    expect(prefsSnapshot().save).toBe("idle");
  });

  it("while the server has not answered, the save is saving — never failed", async () => {
    const answer = held();
    mocks.authedFetch.mockReturnValue(answer.promise);
    const saving = saveNotificationPrefs(OPTED_OUT);
    // The switch has already moved (optimistic), and nothing has failed.
    expect(prefsSnapshot().prefs).toEqual(OPTED_OUT);
    expect(prefsSnapshot().save).toBe("saving");
    answer.answer(ok(WIRE_OPTED_OUT));
    await saving;
  });

  it("a confirmed save is idle and shows what the server holds", async () => {
    mocks.authedFetch.mockResolvedValue(ok(WIRE_OPTED_OUT));
    const { seen, stop } = watchSave();
    await saveNotificationPrefs(OPTED_OUT);
    stop();
    expect(prefsSnapshot()).toMatchObject({ prefs: OPTED_OUT, loaded: true, save: "idle" });
    expect(seen).toEqual(["saving", "idle"]);
  });

  it("a refused save is failed, and the patient's choice stays shown", async () => {
    mocks.authedFetch.mockResolvedValue(refused(503));
    await saveNotificationPrefs(OPTED_OUT);
    expect(prefsSnapshot().save).toBe("failed");
    expect(prefsSnapshot().prefs).toEqual(OPTED_OUT);
  });

  it("an unreachable server is a failed save too", async () => {
    mocks.authedFetch.mockRejectedValue(new TypeError("Network request failed"));
    await saveNotificationPrefs(OPTED_OUT);
    expect(prefsSnapshot().save).toBe("failed");
  });

  it("each retry passes through saving, so every failure is its own change", async () => {
    mocks.authedFetch.mockResolvedValue(refused(503));
    const { seen, stop } = watchSave();
    await saveNotificationPrefs(OPTED_OUT);
    await saveNotificationPrefs(DEFAULT_PREFS);
    stop();
    expect(seen).toEqual(["saving", "failed", "saving", "failed"]);
  });

  it("a combination the screen cannot produce is refused before anything is sent", async () => {
    await saveNotificationPrefs({ optedOut: false, quietStart: "22:00", quietEnd: null });
    expect(mocks.authedFetch).not.toHaveBeenCalled();
    expect(prefsSnapshot().save).toBe("idle");
  });

  it("a server read confirms the shown state and ends a failure", async () => {
    mocks.authedFetch.mockResolvedValueOnce(refused(503));
    await saveNotificationPrefs(OPTED_OUT);
    expect(prefsSnapshot().save).toBe("failed");
    mocks.authedFetch.mockResolvedValueOnce(ok(WIRE_OPTED_OUT));
    await loadNotificationPrefs("hesap-1");
    expect(prefsSnapshot()).toMatchObject({ prefs: OPTED_OUT, loaded: true, save: "idle" });
  });

  it("signing out drops a failure with the working copy", async () => {
    mocks.authedFetch.mockResolvedValue(refused(503));
    await saveNotificationPrefs(OPTED_OUT);
    resetNotificationPrefs();
    expect(prefsSnapshot()).toMatchObject({ prefs: DEFAULT_PREFS, loaded: false, save: "idle" });
  });
});
