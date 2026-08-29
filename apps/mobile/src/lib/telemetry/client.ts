/**
 * The crash client (INT-145; files/10 §4 "crash reports without PHI").
 *
 * Three properties, each of which is a requirement rather than a default:
 *
 * 1. INERT UNTIL CONFIGURED. No DSN, a malformed DSN, or the reporter switched
 *    off, and the client reports a typed reason and sends nothing. It mirrors
 *    `pinningStatus()` in lib/auth/pinning.ts: a reason enum, never a bare
 *    boolean, so "off" always says which off it is.
 * 2. NOTHING TOUCHES DISK. There is no retry queue and no offline spool. An
 *    unsent crash is dropped and counted. A spool would be a file of crash
 *    events on a patient's phone, which is exactly the posture invariant 3
 *    takes about anything sensitive reaching storage — and a crash event is
 *    only non-sensitive because the scrubber made it so, which is a property of
 *    today's scrubber, not of the file that would outlive it.
 * 3. A CRASH REPORTER MAY NEVER CRASH. Every failure path resolves; nothing
 *    here throws into the caller, which is by definition already in a bad way.
 *
 * The transport is injected. The app supplies a `fetch`-backed one from
 * expoTelemetry.ts; tests supply a spy, which is why this module runs in node.
 */
import { authHeader, buildEnvelopeBody } from "./envelope";
import { parseDsn } from "./dsn";
import { buildCrashReport, type TelemetryIdentity } from "./scrub";

export interface CrashTransportRequest {
  readonly url: string;
  readonly headers: Readonly<Record<string, string>>;
  readonly body: string;
}

/** Where an envelope goes. Wiring supplies the real one; tests supply a spy. */
export interface CrashTransport {
  send(request: CrashTransportRequest): Promise<{ ok: boolean }>;
}

/** Why the reporter is off, or where it is on. Never a bare boolean. */
export type CrashClientStatus =
  | { readonly active: false; readonly reason: "not_configured" | "malformed_dsn" | "disabled" }
  | { readonly active: true; readonly endpoint: string };

/** `inert` = nothing was configured; `failed` = configured and did not land. */
export type CaptureOutcome = "sent" | "inert" | "failed";

export interface CrashClient {
  status(): CrashClientStatus;
  captureCrash(raw: unknown): Promise<CaptureOutcome>;
}

export interface CrashClientOptions {
  /** The configured DSN, or null/empty when there is none. */
  readonly dsn: string | null | undefined;
  readonly identity: TelemetryIdentity;
  readonly transport: CrashTransport;
  /** Defaults to on: a configured DSN is itself the opt-in. */
  readonly enabled?: boolean;
  readonly now?: () => number;
}

export function createCrashClient(options: CrashClientOptions): CrashClient {
  const enabled = options.enabled ?? true;
  const dsn = parseDsn(options.dsn);
  const now = options.now ?? (() => Date.now());

  const status: CrashClientStatus = !enabled
    ? { active: false, reason: "disabled" }
    : typeof options.dsn !== "string" || options.dsn.trim() === ""
      ? { active: false, reason: "not_configured" }
      : dsn === null
        ? { active: false, reason: "malformed_dsn" }
        : { active: true, endpoint: dsn.envelopeUrl };

  return {
    status: () => status,
    captureCrash: async (raw: unknown): Promise<CaptureOutcome> => {
      if (!status.active || dsn === null) {
        return "inert";
      }
      const report = buildCrashReport(options.identity, raw);
      const request: CrashTransportRequest = {
        url: dsn.envelopeUrl,
        headers: {
          "Content-Type": "application/x-sentry-envelope",
          "X-Sentry-Auth": authHeader(dsn),
        },
        body: buildEnvelopeBody(dsn, report, now()),
      };
      try {
        const result = await options.transport.send(request);
        return result.ok ? "sent" : "failed";
      } catch {
        // Swallowed on purpose, and without logging the error: the thing we
        // would log is the network error object, and this module's whole
        // premise is that error objects are untrusted (files/10 §3).
        return "failed";
      }
    },
  };
}
