/**
 * INT-583 — the Cihazlarınız screen's model, kept out of the screen so it can
 * be proved in node: the order devices appear in, the 24 h hold on signing
 * other devices out, what each server answer leaves on screen, and which
 * line the new-sign-in notice row shows.
 */
import { describe, expect, it } from "vitest";

import { en } from "../i18n/en";
import { tr } from "../i18n/tr";
import type { DeviceSession, RevokeResult, SessionList, SignOutOthersResult } from "./api";
import {
  INITIAL_SESSIONS_STATE,
  NOTICE_COPY,
  PUSH_NOTICE_BODY,
  deviceLabelKey,
  formatSignInMoment,
  holdFromList,
  holdFromRefusal,
  orderSessions,
  pushNoticeState,
  reloadAfterRegistration,
  reloadsAfter,
  sessionsReducer,
  sessionsView,
  type Notice,
  type SessionsState,
} from "./model";

const NOW = new Date("2026-10-30T12:00:00Z");

function device(id: string, signedInAt: string, current = false, push = false): DeviceSession {
  return { sessionId: id.padEnd(32, "0"), current, signedInAt, push };
}

const HERE = device("aa", "2026-10-01T08:00:00Z", true, true);
const OLDER = device("bb", "2026-09-15T08:00:00Z");
const NEWER = device("cc", "2026-10-29T18:40:00Z");
const NEWEST = device("dd", "2026-10-30T09:12:00Z");

function listOf(sessions: DeviceSession[], after: string | null = null): SessionList {
  return { sessions, signOutOthersAfter: after };
}

function loaded(list: SessionList): SessionsState {
  return sessionsReducer(INITIAL_SESSIONS_STATE, { type: "loaded", result: { ok: true, list } });
}

describe("order: this device first, then the newest sign-in", () => {
  it("puts the current device first even when it is the oldest sign-in", () => {
    expect(orderSessions([OLDER, NEWEST, HERE, NEWER]).map((s) => s.sessionId)).toEqual([
      HERE.sessionId,
      NEWEST.sessionId,
      NEWER.sessionId,
      OLDER.sessionId,
    ]);
  });

  it("does not reorder the caller's array", () => {
    const input = [OLDER, HERE];
    orderSessions(input);
    expect(input).toEqual([OLDER, HERE]);
  });

  it("two sign-ins at the same instant keep one stable order (near miss: tie)", () => {
    const a = device("e1", "2026-10-20T10:00:00Z");
    const b = device("e2", "2026-10-20T10:00:00Z");
    expect(orderSessions([b, a])).toEqual(orderSessions([a, b]));
  });

  it("labels the current device and every other one", () => {
    expect(deviceLabelKey(HERE)).toBe("sessions.thisDevice");
    expect(deviceLabelKey(NEWER)).toBe("sessions.otherDevice");
  });
});

describe("the hold on signing other devices out", () => {
  it("null from the server means free now", () => {
    expect(holdFromList(null, NOW)).toEqual({ held: false });
  });

  it("an instant in the future holds until that instant", () => {
    expect(holdFromList("2026-10-31T09:12:00Z", NOW)).toEqual({
      held: true,
      until: "2026-10-31T09:12:00Z",
    });
  });

  it("an instant already passed is free (near miss: one second ago)", () => {
    expect(holdFromList("2026-10-30T11:59:59Z", NOW)).toEqual({ held: false });
  });

  it("the boundary instant itself is free: the server allows it from that instant", () => {
    expect(holdFromList(NOW.toISOString(), NOW)).toEqual({ held: false });
  });

  it("a refusal's retry_after_s holds until now plus that many seconds", () => {
    expect(holdFromRefusal(3600, NOW)).toEqual({ held: true, until: "2026-10-30T13:00:00.000Z" });
  });

  it("a refusal with no usable number still holds, with no instant to show", () => {
    expect(holdFromRefusal(null, NOW)).toEqual({ held: true, until: null });
  });
});

describe("what the screen shows for a loaded list", () => {
  it("free: every other device can be signed out, and the patient can report", () => {
    const view = sessionsView(loaded(listOf([NEWER, HERE])), NOW);
    expect(view.rows.map((r) => r.sessionId)).toEqual([HERE.sessionId, NEWER.sessionId]);
    expect(view.others).toBe(1);
    expect(view.hold).toEqual({ held: false });
    expect(view.canSignOutOthers).toBe(true);
    expect(view.canReportNotMe).toBe(true);
    expect(view.currentPush).toBe(true);
  });

  it("held: no sign-out of others, but reporting stays open", () => {
    const view = sessionsView(loaded(listOf([NEWER, HERE], "2026-10-31T09:12:00Z")), NOW);
    expect(view.hold).toEqual({ held: true, until: "2026-10-31T09:12:00Z" });
    expect(view.canSignOutOthers).toBe(false);
    expect(view.canReportNotMe).toBe(true);
  });

  it("only this device: nothing to sign out and nothing to report", () => {
    const view = sessionsView(loaded(listOf([HERE])), NOW);
    expect(view.others).toBe(0);
    expect(view.canSignOutOthers).toBe(false);
    expect(view.canReportNotMe).toBe(false);
  });

  it("no list yet: no rows and no actions", () => {
    const view = sessionsView(INITIAL_SESSIONS_STATE, NOW);
    expect(view.rows).toEqual([]);
    expect(view.canSignOutOthers).toBe(false);
    expect(view.canReportNotMe).toBe(false);
    expect(view.currentPush).toBeNull();
  });

  it("a list with no current row has no push answer for this device", () => {
    expect(sessionsView(loaded(listOf([NEWER])), NOW).currentPush).toBeNull();
  });

  it("while a request is out, nothing can be tapped twice", () => {
    const busy = sessionsReducer(loaded(listOf([NEWER, HERE])), { type: "working" });
    const view = sessionsView(busy, NOW);
    expect(view.canSignOutOthers).toBe(false);
    expect(view.canReportNotMe).toBe(false);
  });
});

describe("loading", () => {
  it("a failed load drops any list it cannot vouch for and says so", () => {
    const state = sessionsReducer(loaded(listOf([NEWER, HERE])), {
      type: "loaded",
      result: { ok: false, error: "unreachable" },
    });
    expect(state.list).toBeNull();
    expect(state.loadFailed).toBe(true);
  });

  it("a fresh list replaces a refusal hold: the server's list is the newer word", () => {
    let state = loaded(listOf([NEWER, HERE]));
    state = sessionsReducer(state, {
      type: "revoked",
      result: { ok: false, error: "session_too_new", retryAfterS: 600 },
      now: NOW,
    });
    expect(sessionsView(state, NOW).hold.held).toBe(true);
    state = sessionsReducer(state, { type: "loaded", result: { ok: true, list: listOf([HERE]) } });
    expect(sessionsView(state, NOW).hold).toEqual({ held: false });
    expect(state.loadFailed).toBe(false);
  });
});

describe("signing one other device out", () => {
  const start = sessionsReducer(loaded(listOf([NEWER, HERE])), { type: "working" });
  const after = (result: RevokeResult) =>
    sessionsReducer(start, { type: "revoked", result, now: NOW });

  it("204 says that device is signed out", () => {
    const state = after({ ok: true });
    expect(state.notice).toBe("deviceSignedOut");
    expect(state.busy).toBe(false);
  });

  it("404 says it was already gone", () => {
    expect(after({ ok: false, error: "not_found" }).notice).toBe("gone");
  });

  it("403 session_too_new holds calmly instead of failing", () => {
    const state = after({ ok: false, error: "session_too_new", retryAfterS: 600 });
    expect(state.notice).toBe("held");
    expect(sessionsView(state, NOW).hold).toEqual({
      held: true,
      until: "2026-10-30T12:10:00.000Z",
    });
  });

  it("unreachable says the request did not go", () => {
    expect(after({ ok: false, error: "unreachable" }).notice).toBe("actionFailed");
  });
});

describe("signing every other device out, and 'that wasn't me'", () => {
  const base = loaded(listOf([NEWER, HERE]));

  it("the report takes a confirmation step first", () => {
    const armed = sessionsReducer(base, { type: "confirmNotMe" });
    expect(armed.confirming).toBe(true);
    expect(sessionsReducer(armed, { type: "cancelNotMe" }).confirming).toBe(false);
  });

  const cases: [boolean, SignOutOthersResult, Notice][] = [
    [false, { ok: true, signedOut: 1 }, "othersSignedOut"],
    [true, { ok: true, signedOut: 1 }, "reported"],
    [false, { ok: false, error: "session_too_new", retryAfterS: 60 }, "held"],
    [true, { ok: false, error: "session_too_new", retryAfterS: 60 }, "reportedHeld"],
    [false, { ok: false, error: "unreachable" }, "actionFailed"],
    [true, { ok: false, error: "unreachable" }, "reportFailed"],
  ];

  it.each(cases)("not_me=%s, %j -> %s", (notMe, result, notice) => {
    const armed = sessionsReducer(base, { type: "confirmNotMe" });
    const state = sessionsReducer(sessionsReducer(armed, { type: "working" }), {
      type: "signedOutOthers",
      result,
      notMe,
      now: NOW,
    });
    expect(state.notice).toBe(notice);
    expect(state.confirming).toBe(false);
    expect(state.busy).toBe(false);
  });

  it("a report made during the hold says it was received, and shows the hold", () => {
    const state = sessionsReducer(base, {
      type: "signedOutOthers",
      result: { ok: false, error: "session_too_new", retryAfterS: 60 },
      notMe: true,
      now: NOW,
    });
    expect(sessionsView(state, NOW).hold).toEqual({
      held: true,
      until: "2026-10-30T12:01:00.000Z",
    });
  });
});

describe("what reloads the list after an action", () => {
  it("every answer the server gave reloads; a request that never landed does not", () => {
    expect(reloadsAfter({ ok: true })).toBe(true);
    expect(reloadsAfter({ ok: true, signedOut: 2 })).toBe(true);
    expect(reloadsAfter({ ok: false, error: "not_found" })).toBe(true);
    expect(reloadsAfter({ ok: false, error: "session_too_new", retryAfterS: 5 })).toBe(true);
    expect(reloadsAfter({ ok: false, error: "unreachable" })).toBe(false);
  });
});

describe("what reloads the list after this device registers", () => {
  const listed = (push: boolean) =>
    ({ ok: true, list: listOf([{ ...HERE, push }, NEWER]) }) as const;

  it("a fresh registration the list does not show yet reloads", () => {
    expect(reloadAfterRegistration(listed(false), "registered")).toBe(true);
  });

  it("a registration the list already shows does not reload (near miss)", () => {
    expect(reloadAfterRegistration(listed(true), "registered")).toBe(false);
  });

  it("no registration, or no list, does not reload", () => {
    for (const outcome of ["skipped", "denied", "unbound", "failed"] as const) {
      expect(reloadAfterRegistration(listed(false), outcome), outcome).toBe(false);
    }
    expect(reloadAfterRegistration({ ok: false, error: "unreachable" }, "registered")).toBe(false);
  });
});

describe("every notice has copy in both catalogues, and failures are errors", () => {
  it("each notice names a real key", () => {
    for (const [notice, copy] of Object.entries(NOTICE_COPY)) {
      expect(tr[copy.key], notice).toBeDefined();
      expect(en[copy.key], notice).toBeDefined();
    }
  });

  it("the two failures are announced as errors; the rest as status", () => {
    expect(NOTICE_COPY.actionFailed.tone).toBe("error");
    expect(NOTICE_COPY.reportFailed.tone).toBe("error");
    for (const notice of ["othersSignedOut", "deviceSignedOut", "reported", "gone"] as const) {
      expect(NOTICE_COPY[notice].tone, notice).toBe("status");
    }
  });

  it("a failed report never reads as a received one (near miss)", () => {
    expect(NOTICE_COPY.reportFailed.key).not.toBe(NOTICE_COPY.reported.key);
    expect(tr[NOTICE_COPY.reportFailed.key]).not.toBe(tr[NOTICE_COPY.reported.key]);
  });
});

describe("sign-in time, in Türkiye's zone and the patient's language", () => {
  it("prints the instant in Europe/Istanbul, in Turkish", () => {
    expect(formatSignInMoment("2026-10-30T09:12:00Z", "tr")).toBe("30 Ekim 2026 12:12");
  });

  it("crosses midnight by Istanbul's clock, not UTC's (near miss: 22:30 UTC)", () => {
    expect(formatSignInMoment("2026-10-29T22:30:00Z", "tr")).toBe("30 Ekim 2026 01:30");
  });

  it("follows the English catalogue when that is the language", () => {
    expect(formatSignInMoment("2026-10-30T09:12:00Z", "en")).toContain("30 October 2026");
    expect(formatSignInMoment("2026-10-30T09:12:00Z", "en")).toContain("12:12");
  });

  it("an unreadable instant prints nothing rather than a wrong date", () => {
    expect(formatSignInMoment("not a date", "tr")).toBe("");
  });
});

describe("the new-sign-in notice row", () => {
  it("undetermined offers the enable button", () => {
    expect(pushNoticeState("undetermined", false, false)).toBe("offer");
  });

  it("denied explains Settings", () => {
    expect(pushNoticeState("denied", false, false)).toBe("denied");
  });

  it("granted and registered with the server is on", () => {
    expect(pushNoticeState("granted", true, false)).toBe("on");
  });

  it("granted but not registered with the server is not on (near miss)", () => {
    expect(pushNoticeState("granted", false, false)).toBe("notRegistered");
    expect(pushNoticeState("granted", null, false)).toBe("notRegistered");
  });

  it("a device that cannot receive them says so", () => {
    expect(pushNoticeState("unavailable", false, false)).toBe("unavailable");
  });

  it("a shared clinic device never offers them, whatever the permission", () => {
    for (const permission of ["granted", "denied", "undetermined", "unavailable"] as const) {
      expect(pushNoticeState(permission, true, true), permission).toBe("unavailable");
    }
  });

  it("before the permission is read the row shows nothing", () => {
    expect(pushNoticeState(null, true, false)).toBeNull();
  });

  it("every state has its explanation in both catalogues", () => {
    for (const [state, key] of Object.entries(PUSH_NOTICE_BODY)) {
      expect(tr[key], state).toBeDefined();
      expect(en[key], state).toBeDefined();
    }
  });
});
