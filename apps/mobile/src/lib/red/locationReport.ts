/**
 * The patient's answer to the one location question reaches the server
 * (INT-475; files/02 §5.3 Axis 3; files/04 §8.1 rule 7; LD-05; CLAUDE.md
 * invariants 6, 21).
 *
 * Under UNKNOWN a RED asks "Şu anda hastanede misiniz?". "Evet" sends it to
 * ON_SITE, where the clinic notification is the primary channel and fires
 * automatically — "Görevlilere haber verildi." is only true once the server has
 * the answer. "Hayır" sends it to REMOTE, which notifies no staff but is still
 * the patient's answer and is recorded. A late "evet" after the no-answer wait
 * took the REMOTE branch is honoured (LD-05) and posted then. The wait's own
 * expiry is not something the patient said, so it is never posted.
 *
 * Fire-and-forget with retry: the RED is already on the screen, from the store,
 * before this request starts, and nothing the screen shows depends on its
 * response. `observe` returns at once; delivery retries with the reconnect
 * policy's capped, jittered backoff while the server is unreachable or busy, or a
 * request outlives `LOCATION_REPORT_TIMEOUT_MS`, and stops at the first
 * acceptance, at a refusal no retry can fix, or after
 * `LOCATION_REPORT_MAX_ATTEMPTS`. One answer is sent once; the server keeps one
 * staff notification per RED whatever arrives twice, so an abandoned request that
 * lands late is harmless.
 *
 * Ids and the branch only: the RED's session, visit and rule ids and ON_SITE or
 * REMOTE. No answer value, no words, and nothing here logs (invariant 6).
 */
import { backoffDelayMs } from "../livekit/reconnect";
import type { HopTransport } from "./hop";
import { redScreen, type RedState, type RedStore } from "./store";

export const LOCATION_PATH = "/v1/triage/red-location";

/**
 * How many times one answer is offered to the server before the device gives
 * up. An engineering bound, not a clinical value: with the reconnect policy's
 * full-jitter delays (each capped at 8 s) the waits total at most about two
 * minutes and about one on average, past files/02 §8.2's 60 s RED-to-inbox
 * budget, while the patient is already acting on the screen.
 */
export const LOCATION_REPORT_MAX_ATTEMPTS = 20;

/**
 * How long one request may hang before it is abandoned and offered again. An
 * engineering bound, not a clinical value: a hung connection must not hold up the
 * retries, and the server's answer to a duplicate is the same entry.
 */
export const LOCATION_REPORT_TIMEOUT_MS = 10_000;

/** The body the server takes: ids and the branch target, nothing else. */
export interface LocationReport {
  readonly session_id: string;
  readonly visit_id: string;
  readonly rule_id: string;
  readonly location: "ON_SITE" | "REMOTE";
}

/**
 * The report a RED state owes, or null. Only the patient's own answer to an
 * asked question is one: "evet" is ON_SITE and "hayır" REMOTE, the branches every
 * served question carries (the catalog decoder refuses any other).
 */
export function locationReportFor(state: RedState | null): LocationReport | null {
  if (state === null || state.trigger.location !== "UNKNOWN") {
    return null;
  }
  if (state.answer !== "inHospital" && state.answer !== "notInHospital") {
    return null;
  }
  return {
    session_id: state.origin.sessionId,
    visit_id: state.origin.visitId,
    rule_id: state.trigger.ruleId,
    location: state.answer === "inHospital" ? "ON_SITE" : "REMOTE",
  };
}

/** Worth trying again: no answer, or the server is down, busy or timed out. */
function retriable(status: number): boolean {
  return status >= 500 || status === 408 || status === 429;
}

/** One request's deadline: `expired` resolves when it passes; `cancel` disarms it. */
export interface RequestDeadline {
  readonly expired: Promise<void>;
  readonly cancel: () => void;
}

export interface LocationReporterOptions {
  readonly transport: HopTransport;
  /** Injected so a test runs every retry without waiting. */
  readonly sleep?: (ms: number) => Promise<void>;
  /** Must return [0,1). */
  readonly jitter?: () => number;
  /** Injected so a test decides when a request has hung too long. */
  readonly timeout?: (ms: number) => RequestDeadline;
}

export interface LocationReporter {
  /** Look at the store's state; post the answer it owes, once. Never waits. */
  observe: (state: RedState | null) => void;
}

const realSleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

function realTimeout(ms: number): RequestDeadline {
  let handle: ReturnType<typeof setTimeout> | undefined;
  const expired = new Promise<void>((resolve) => {
    handle = setTimeout(resolve, ms);
  });
  return { expired, cancel: () => clearTimeout(handle) };
}

/** The last answer a delivery got: its status and body, or nothing at all. */
interface Delivered {
  readonly status: number | null;
  readonly bytes: Uint8Array | null;
}

/**
 * Offer one body to `path` until it is taken, refused for good, or out of tries.
 * Resolves with the last answer, so a caller that must show the outcome can.
 */
function createDelivery(
  {
    transport,
    sleep = realSleep,
    jitter = Math.random,
    timeout = realTimeout,
  }: LocationReporterOptions,
  path: string,
): (body: string) => Promise<Delivered> {
  /** One request: its answer, or null when it failed or hung past its deadline. */
  const attempt = async (body: string): Promise<{ status: number; bytes: Uint8Array } | null> => {
    const deadline = timeout(LOCATION_REPORT_TIMEOUT_MS);
    try {
      return await Promise.race([transport(path, body), deadline.expired.then(() => null)]);
    } catch {
      return null; // unreachable: the next attempt, after the backoff
    } finally {
      deadline.cancel();
    }
  };
  const deliver = async (body: string): Promise<Delivered> => {
    let last: Delivered = { status: null, bytes: null };
    for (let tries = 1; tries <= LOCATION_REPORT_MAX_ATTEMPTS; tries += 1) {
      const answer = await attempt(body);
      if (answer !== null) {
        last = answer;
        if (!retriable(answer.status)) {
          return answer;
        }
      }
      if (tries < LOCATION_REPORT_MAX_ATTEMPTS) {
        await sleep(backoffDelayMs(tries, jitter));
      }
    }
    return last;
  };
  return deliver;
}

export function createLocationReporter(options: LocationReporterOptions): LocationReporter {
  const sent = new Set<string>();
  const deliver = createDelivery(options, LOCATION_PATH);
  return {
    observe: (state) => {
      const report = locationReportFor(state);
      if (report === null) {
        return;
      }
      const body = JSON.stringify(report);
      if (sent.has(body)) {
        return;
      }
      sent.add(body);
      void deliver(body);
    },
  };
}

/** Report every answer the store takes. Returns the unsubscribe. */
export function subscribeLocationReports(
  store: Pick<RedStore, "subscribe" | "getSnapshot">,
  reporter: LocationReporter,
): () => void {
  return store.subscribe(() => reporter.observe(store.getSnapshot()));
}

/** The route a staff-control press goes to (INT-602; intake_api.red_notify). */
export const STAFF_CALL_PATH = "/v1/triage/red-staff-call";

/** The body a press sends: this RED's ids, nothing else (invariant 6). */
export interface StaffCall {
  readonly session_id: string;
  readonly visit_id: string;
  readonly rule_id: string;
}

/**
 * The staff control under ON_SITE (INT-602; files/02 §5.3 action table:
 * "Hastanedeyim — personele bildir", which stays on screen "so the patient can
 * see that it already happened").
 *
 * A press goes to its own route, which puts this RED's one on-site staff
 * notification in the clinic Safety inbox and audits the press as a press
 * (`api.triage.red_staff_called`), never as a location answer. The server keeps
 * one notification per RED, so a repeat press pages nobody twice. Null unless
 * the screen shows an ON_SITE action.
 */
export function staffCallFor(state: RedState | null): StaffCall | null {
  if (state === null) {
    return null;
  }
  const screen = redScreen(state);
  if (screen.kind !== "act" || !screen.callStaff) {
    return null;
  }
  return {
    session_id: state.origin.sessionId,
    visit_id: state.origin.visitId,
    rule_id: state.trigger.ruleId,
  };
}

/**
 * What the patient is shown about their press. Never silent:
 * - `idle`: nothing pressed yet for this RED;
 * - `sending`: a request is out, or a retry waits;
 * - `sent`: only after the server answered 2xx with `staffNotified: true`;
 * - `failed`: refused for good (a 4xx: rule not served, no consent, signed out),
 *   out of retries, or an answer that does not say staff were notified.
 */
export type StaffCallPhase = "idle" | "sending" | "sent" | "failed";

/** The caller's state: which RED it is about, and where its press stands. */
export interface StaffCallSnapshot {
  readonly key: string | null;
  readonly phase: StaffCallPhase;
}

export interface StaffCaller {
  /** The patient pressed the staff control. Never waits. */
  call: (state: RedState | null) => void;
  getSnapshot: () => StaffCallSnapshot;
  subscribe: (listener: () => void) => () => void;
}

/** The phase to show for this RED: another RED's press shows nothing. */
export function staffCallPhase(
  snapshot: StaffCallSnapshot,
  state: RedState | null,
): StaffCallPhase {
  const call = staffCallFor(state);
  return call !== null && snapshot.key === JSON.stringify(call) ? snapshot.phase : "idle";
}

/** Whether a final answer says staff were notified: 2xx and `staffNotified: true`. */
function confirmed({ status, bytes }: Delivered): boolean {
  if (status === null || status < 200 || status >= 300 || bytes === null) {
    return false;
  }
  try {
    const body: unknown = JSON.parse(new TextDecoder().decode(bytes));
    return (
      typeof body === "object" &&
      body !== null &&
      (body as Record<string, unknown>).staffNotified === true
    );
  } catch {
    return false;
  }
}

export function createStaffCaller(options: LocationReporterOptions): StaffCaller {
  const deliver = createDelivery(options, STAFF_CALL_PATH);
  let snapshot: StaffCallSnapshot = { key: null, phase: "idle" };
  const listeners = new Set<() => void>();
  const set = (next: StaffCallSnapshot) => {
    snapshot = next;
    for (const listener of listeners) {
      listener();
    }
  };
  return {
    getSnapshot: () => snapshot,
    subscribe: (listener) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    call: (state) => {
      const call = staffCallFor(state);
      if (call === null) {
        return;
      }
      const key = JSON.stringify(call);
      if (snapshot.key === key && snapshot.phase === "sending") {
        return; // one request in flight
      }
      if (snapshot.key === key && snapshot.phase === "sent") {
        // A repeat press after a confirmed send pages nobody (one notification
        // per RED): re-show what already happened, never imply a new page.
        set({ key, phase: "sent" });
        return;
      }
      set({ key, phase: "sending" });
      void deliver(key).then(
        (answer) => set({ key, phase: confirmed(answer) ? "sent" : "failed" }),
        () => set({ key, phase: "failed" }),
      );
    },
  };
}
