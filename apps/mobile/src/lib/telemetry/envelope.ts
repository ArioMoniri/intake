/**
 * The GlitchTip envelope (INT-145).
 *
 * GlitchTip speaks the Sentry envelope protocol: a newline-delimited body of
 * one header line followed by (item header, item payload) pairs. We build it
 * ourselves rather than taking a vendor SDK, and that choice is the control,
 * not a preference:
 *
 * - An SDK's value is precisely the behaviour we must not have — automatic
 *   breadcrumbs from navigation and network, `include_local_variables`,
 *   screenshot capture, session replay. Turning those off leaves the code in
 *   the bundle and one config regression away from live. INT-145 requires
 *   replay to be UNREACHABLE, and the only way to be sure is for the capture
 *   surfaces not to exist.
 * - A hand-built envelope makes the allow-list total: the payload is exactly
 *   the fields written below, over a `CrashReport` that was itself constructed
 *   field by field. There is no "rest of the event" for anything to hide in.
 * - It adds no dependency, so there is no new licence to verify and no new
 *   transitive tree inside a KVKK-scoped app (files/10 §4).
 *
 * EXACTLY ONE ITEM, AND ITS TYPE IS `event`. No attachment item, no replay
 * item, no profile item — those item types have no constructor here.
 */
import type { CrashReport } from "./scrub";

/** The three things a parsed DSN yields. Nothing else is kept from it. */
export interface DsnParts {
  readonly publicKey: string;
  readonly projectId: string;
  readonly envelopeUrl: string;
}

/** The client name GlitchTip records against the event. */
export const SDK_NAME = "intake.mobile.telemetry";
export const SDK_VERSION = "1";

/** The auth header GlitchTip expects. The public key is not a secret — it
 * identifies the project; the DSN carries no secret half (see dsn.ts). */
export function authHeader(dsn: DsnParts): string {
  return [
    "Sentry sentry_version=7",
    `sentry_client=${SDK_NAME}/${SDK_VERSION}`,
    `sentry_key=${dsn.publicKey}`,
  ].join(", ");
}

/** The DSN, reassembled from the two halves we kept. A relay in front of
 * GlitchTip reads it off the envelope header; it names the project and carries
 * no secret, because dsn.ts refuses a DSN that has a secret half at all. */
function dsnString(dsn: DsnParts): string {
  const origin = dsn.envelopeUrl.split("/api/")[0];
  return `${origin.replace("://", `://${dsn.publicKey}@`)}/${dsn.projectId}`;
}

/**
 * 32 lowercase hex, from allow-listed material only: the 16-hex fingerprint
 * and the send time. Two reports of the same crash site in the same
 * millisecond share an id, which is the right answer — the tracker folds them
 * into one event, and they are one event.
 */
function eventId(report: CrashReport, sentAtMs: number): string {
  const stamp = Math.max(0, Math.trunc(sentAtMs)).toString(16);
  return report.fingerprint + stamp.padStart(16, "0").slice(-16);
}

/**
 * The event payload — the complete list of what is sent about a crash.
 *
 * `exception.values[].value` carries the error CODE, not a message. That is
 * the field a tracker renders as the headline, and putting a shape-validated
 * `[a-z_]` identifier there is what makes the report readable without a
 * sentence ever being eligible to appear in it (files/10 §3, `SafeError`).
 */
function eventPayload(report: CrashReport, sentAtMs: number, id: string): Record<string, unknown> {
  const timestamp = (report.timestampMs > 0 ? report.timestampMs : sentAtMs) / 1000;
  return {
    event_id: id,
    timestamp,
    platform: "javascript",
    level: "error",
    logger: SDK_NAME,
    fingerprint: [report.fingerprint],
    tags: report.tags,
    exception: {
      values: [
        {
          type: report.exceptionType ?? "ClientError",
          value: report.errorCode,
          stacktrace: { frames: [...report.frames].reverse() },
        },
      ],
    },
    breadcrumbs: { values: report.breadcrumbs },
    sdk: { name: SDK_NAME, version: SDK_VERSION },
  };
}

/**
 * Serialise one crash into an envelope body.
 *
 * `JSON.stringify` is what guarantees the newline framing holds: every value
 * in the payload has already passed a shape with no newline in its character
 * class, and any that somehow did would be escaped rather than splitting the
 * frame.
 */
export function buildEnvelopeBody(dsn: DsnParts, report: CrashReport, sentAtMs = 0): string {
  const id = eventId(report, sentAtMs);
  const header = { event_id: id, sent_at: new Date(sentAtMs).toISOString(), dsn: dsnString(dsn) };
  const itemHeader = { type: "event", content_type: "application/json" };
  return [
    JSON.stringify(header),
    JSON.stringify(itemHeader),
    JSON.stringify(eventPayload(report, sentAtMs, id)),
  ].join("\n");
}
