/**
 * INT-583 — the Cihazlarınız screen's model: the order devices appear in, the
 * hold on signing other devices out, what each server answer leaves on
 * screen, and which line the new-sign-in notice row shows.
 *
 * The hold. A session signed in less than 24 hours ago cannot sign OTHER
 * devices out: otherwise someone who has just got in could lock the real
 * patient out of their own phone. The server enforces it; this model only
 * shows it calmly — as the instant from which the button works — instead of
 * as a failure. A "that wasn't me" report made during the hold is still
 * recorded by the server, so the screen says it was received.
 *
 * Pure: the screen holds the state in a reducer and renders `sessionsView`.
 */
import { APP_TIME_ZONE } from "../clock";
import type { Locale, MessageKey } from "../i18n";
import type { PushPermission } from "../push/plan";
import type { PushOutcome } from "../push/registration";
import type {
  DeviceSession,
  ListResult,
  RevokeResult,
  SessionList,
  SignOutOthersResult,
} from "./api";

export type Hold = { held: false } | { held: true; until: string | null };

const FREE: Hold = { held: false };

/** This device first, then the newest sign-in; ties by id, so the order is stable. */
export function orderSessions(sessions: readonly DeviceSession[]): DeviceSession[] {
  return [...sessions].sort((a, b) => {
    if (a.current !== b.current) {
      return a.current ? -1 : 1;
    }
    const byTime = Date.parse(b.signedInAt) - Date.parse(a.signedInAt);
    if (byTime !== 0) {
      return byTime;
    }
    return a.sessionId < b.sessionId ? -1 : a.sessionId > b.sessionId ? 1 : 0;
  });
}

export function deviceLabelKey(session: DeviceSession): MessageKey {
  return session.current ? "sessions.thisDevice" : "sessions.otherDevice";
}

/** The server's `sign_out_others_after`, read at `now`. The instant itself is free. */
export function holdFromList(after: string | null, now: Date): Hold {
  if (after === null || Date.parse(after) <= now.getTime()) {
    return FREE;
  }
  return { held: true, until: after };
}

/** A 403 `session_too_new`: held for `retryAfterS` seconds, or for an unknown while. */
export function holdFromRefusal(retryAfterS: number | null, now: Date): Hold {
  if (retryAfterS === null) {
    return { held: true, until: null };
  }
  return { held: true, until: new Date(now.getTime() + retryAfterS * 1000).toISOString() };
}

function stillHeld(hold: Hold, now: Date): Hold {
  if (!hold.held || hold.until === null) {
    return hold;
  }
  return Date.parse(hold.until) > now.getTime() ? hold : FREE;
}

/** Held if either says so; the latest known instant wins. */
function eitherHold(a: Hold, b: Hold): Hold {
  if (!a.held) {
    return b;
  }
  if (!b.held) {
    return a;
  }
  if (a.until === null || b.until === null) {
    return { held: true, until: a.until ?? b.until };
  }
  return Date.parse(a.until) >= Date.parse(b.until) ? a : b;
}

/** What the screen says after an action. */
export type Notice =
  | "othersSignedOut"
  | "deviceSignedOut"
  | "reported"
  | "reportedHeld"
  | "held"
  | "gone"
  | "actionFailed"
  | "reportFailed";

export const NOTICE_COPY: Record<Notice, { key: MessageKey; tone: "status" | "error" }> = {
  othersSignedOut: { key: "sessions.done.others", tone: "status" },
  deviceSignedOut: { key: "sessions.done.device", tone: "status" },
  reported: { key: "sessions.done.reported", tone: "status" },
  reportedHeld: { key: "sessions.done.reportedHeld", tone: "status" },
  held: { key: "sessions.hold.notYet", tone: "status" },
  gone: { key: "sessions.done.gone", tone: "status" },
  actionFailed: { key: "sessions.error.actionUnsent", tone: "error" },
  reportFailed: { key: "sessions.error.reportUnsent", tone: "error" },
};

export interface SessionsState {
  /** The server's list; null before the first load and after a failed one. */
  list: SessionList | null;
  loadFailed: boolean;
  /** A hold learned from a 403, until the next list replaces it. */
  refusal: Hold;
  notice: Notice | null;
  /** The "that wasn't me" confirmation step is open. */
  confirming: boolean;
  /** A request is out; nothing can be tapped twice. */
  busy: boolean;
}

export const INITIAL_SESSIONS_STATE: SessionsState = {
  list: null,
  loadFailed: false,
  refusal: FREE,
  notice: null,
  confirming: false,
  busy: false,
};

export type SessionsEvent =
  | { type: "loaded"; result: ListResult }
  | { type: "confirmNotMe" }
  | { type: "cancelNotMe" }
  | { type: "working" }
  | { type: "revoked"; result: RevokeResult; now: Date }
  | { type: "signedOutOthers"; result: SignOutOthersResult; notMe: boolean; now: Date };

function revokeNotice(result: RevokeResult): Notice {
  if (result.ok) {
    return "deviceSignedOut";
  }
  switch (result.error) {
    case "not_found":
      return "gone";
    case "session_too_new":
      return "held";
    case "unreachable":
      return "actionFailed";
  }
}

function signOutOthersNotice(result: SignOutOthersResult, notMe: boolean): Notice {
  if (result.ok) {
    return notMe ? "reported" : "othersSignedOut";
  }
  if (result.error === "session_too_new") {
    return notMe ? "reportedHeld" : "held";
  }
  return notMe ? "reportFailed" : "actionFailed";
}

function refusalOf(result: RevokeResult | SignOutOthersResult, now: Date, prior: Hold): Hold {
  return !result.ok && result.error === "session_too_new"
    ? holdFromRefusal(result.retryAfterS, now)
    : prior;
}

export function sessionsReducer(state: SessionsState, event: SessionsEvent): SessionsState {
  switch (event.type) {
    case "loaded":
      return event.result.ok
        ? { ...state, list: event.result.list, loadFailed: false, refusal: FREE }
        : { ...state, list: null, loadFailed: true };
    case "confirmNotMe":
      return { ...state, confirming: true, notice: null };
    case "cancelNotMe":
      return { ...state, confirming: false };
    case "working":
      return { ...state, busy: true, notice: null };
    case "revoked":
      return {
        ...state,
        busy: false,
        notice: revokeNotice(event.result),
        refusal: refusalOf(event.result, event.now, state.refusal),
      };
    case "signedOutOthers":
      return {
        ...state,
        busy: false,
        confirming: false,
        notice: signOutOthersNotice(event.result, event.notMe),
        refusal: refusalOf(event.result, event.now, state.refusal),
      };
  }
}

/** Every answer the server gave changes the list; a request that never landed does not. */
export function reloadsAfter(result: RevokeResult | SignOutOthersResult): boolean {
  return result.ok || result.error !== "unreachable";
}

/**
 * What a list tells a registration run about this device: its `push` flag,
 * or undefined when there is no list or no current row. Undefined is the
 * run's "unknown", under which a denied permission still deletes.
 */
export function knownRegistration(result: ListResult): boolean | undefined {
  if (!result.ok) {
    return undefined;
  }
  return result.list.sessions.find((session) => session.current)?.push;
}

/**
 * The list loads first and this device's silent registration runs after it,
 * so a slow native token call never holds the list back. When the
 * registration lands and the list did not show it yet, one reload brings the
 * server's `push` flag for this device up to date.
 */
export function reloadAfterRegistration(result: ListResult, outcome: PushOutcome): boolean {
  if (outcome !== "registered" || !result.ok) {
    return false;
  }
  return !result.list.sessions.some((session) => session.current && session.push);
}

export interface SessionsView {
  rows: DeviceSession[];
  /** Devices other than this one. */
  others: number;
  hold: Hold;
  canSignOutOthers: boolean;
  canReportNotMe: boolean;
  /** Whether the server holds a registration for THIS device; null when unknown. */
  currentPush: boolean | null;
  /** Whether the server has a push channel wired; null before a list. */
  noticesOn: boolean | null;
  /**
   * "Bu girişi ben yapmadım" is shown once a list is loaded, other devices or
   * not: a patient who got a notice may find the intruder already gone from
   * the list (it signed itself out, or its session ended), and must still be
   * able to report it.
   */
  showReport: boolean;
}

export function sessionsView(state: SessionsState, now: Date): SessionsView {
  const rows = state.list === null ? [] : orderSessions(state.list.sessions);
  const others = rows.filter((row) => !row.current).length;
  const listHold = state.list === null ? FREE : holdFromList(state.list.signOutOthersAfter, now);
  const hold = eitherHold(listHold, stillHeld(state.refusal, now));
  const open = others > 0 && !state.busy;
  const showReport = state.list !== null;
  return {
    rows,
    others,
    hold,
    canSignOutOthers: open && !hold.held,
    canReportNotMe: showReport && !state.busy,
    showReport,
    currentPush: rows.find((row) => row.current)?.push ?? null,
    noticesOn: state.list === null ? null : state.list.noticesOn,
  };
}

/**
 * "30 Ekim 2026 12:12": the instant on Türkiye's clock (clock.ts), whatever
 * zone the phone is set to, in the patient's language. Not a clinical
 * quantity, and no number in it is grouped (invariant 22). An unreadable
 * instant prints nothing rather than a wrong date.
 */
export function formatSignInMoment(iso: string, locale: Locale): string {
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) {
    return "";
  }
  return new Intl.DateTimeFormat(locale === "tr" ? "tr-TR" : "en-GB", {
    day: "numeric",
    month: "long",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    timeZone: APP_TIME_ZONE,
  }).format(at);
}

/** Which line the new-sign-in notice row shows; null before the permission is read. */
export type PushNoticeState = "offer" | "on" | "denied" | "notRegistered" | "unavailable";

/**
 * `noticesOn` is the list's word on whether the server can send at all. A
 * registered device on a server with no channel is not "on": nothing would
 * reach it. Null (no list yet) leaves the row as the permission and the
 * registration say.
 */
export function pushNoticeState(
  permission: PushPermission | null,
  currentPush: boolean | null,
  sharedDevice: boolean,
  noticesOn: boolean | null,
): PushNoticeState | null {
  if (sharedDevice) {
    return "unavailable";
  }
  switch (permission) {
    case null:
      return null;
    case "undetermined":
      // no channel on the server: the offer's promise could not be kept
      return noticesOn === false ? "notRegistered" : "offer";
    case "denied":
      return "denied";
    case "unavailable":
      return "unavailable";
    case "granted":
      return currentPush === true && noticesOn !== false ? "on" : "notRegistered";
  }
}

export const PUSH_NOTICE_BODY: Record<PushNoticeState, MessageKey> = {
  offer: "sessions.push.offerBody",
  on: "sessions.push.onBody",
  denied: "sessions.push.deniedBody",
  notRegistered: "sessions.push.notRegisteredBody",
  unavailable: "sessions.push.unavailableBody",
};
