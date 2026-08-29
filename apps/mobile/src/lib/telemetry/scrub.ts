/**
 * The crash-report scrubber (INT-145; CLAUDE.md invariant 6; files/10 §3–§4).
 *
 * A crash report is the single most likely place for PHI to leave the device.
 * files/10 §3 names the server-side version of this ("the leak nobody
 * mentioned"): an SDK serialises local variables into the event, so a local
 * named `pcm` posts patient voice to the tracker. On the client the same three
 * limbs leak by default — stack frames capture locals, breadcrumbs capture
 * screen text, and a network breadcrumb captures a URL with its query string.
 *
 * THIS IS AN ALLOW-LIST, NOT A BLOCKLIST, AND THE DIFFERENCE IS THE WHOLE
 * DESIGN. A blocklist redacts the identifiers somebody thought of; everything
 * nobody thought of ships. So there is no regex over the outgoing payload here.
 * Instead the payload is CONSTRUCTED: `buildCrashReport` takes the crash event
 * as `unknown`, reads a closed set of keys out of it, validates each against
 * that key's own shape, and assembles a fresh object. A field that is not
 * enumerated below has no code path to the wire — not a suppressed one, none.
 *
 * Three consequences worth stating plainly, because each looks like a bug:
 *
 * 1. THE EXCEPTION MESSAGE IS NOT SENT. `exception.values[].value` is where a
 *    Pydantic-style error puts the patient's sentence and where a thrown
 *    `Error(...)` puts whatever string was to hand. files/10 §3's `SafeError`
 *    boundary says an exception becomes `{error_code, correlation_id}` before
 *    any reporter sees it; this module assumes that boundary may have been
 *    missed and does not read the message at all. What GlitchTip shows instead
 *    is the error CODE — a shape-validated `[a-z_]` identifier.
 * 2. FRAME LOCALS, CONTEXT LINES AND SOURCE SNIPPETS ARE NOT READ. A frame
 *    contributes four code coordinates: module, function, line, column.
 * 3. THERE IS NO `extra`, NO `contexts`, NO `user` AND NO `request`. Those
 *    limbs have no enumerated keys, so nothing in them can be reached.
 *
 * The tag allow-list is split by WHO may supply a key. Identity keys are set
 * once when the client is constructed, from the app's own build metadata
 * (files/10 §6: "Mobile and web report app_version, build_id, sbom_digest in
 * telemetry"). Event keys are the only ones a crash event may set. Both go
 * through `TAG_SHAPES`, because an allow-listed KEY is not enough: `05321234567`
 * is a well-formed string, and a shared "any short token" shape would let a
 * phone number ride in on a legitimate key name.
 *
 * tests/mobile/test_crash_scrub.py holds the read set and both allow-lists
 * against this file, so widening either is a visible, reviewable change.
 */
import { sha256 } from "@noble/hashes/sha2.js";

/** Set when the crash event's own code is missing or unreadable. Never text. */
export const UNCLASSIFIED_ERROR_CODE = "unclassified_client_error";

/** Supplied by the client's own construction, never by a crash event. */
export const IDENTITY_TAG_KEYS = [
  "app_version",
  "build_id",
  "sbom_digest",
  "environment",
  "release_channel",
  "platform",
  "os_version",
  "device_model",
  "tenant_id",
] as const;

/** The only tags a crash event may set. Ids and codes; no content. */
export const EVENT_TAG_KEYS = [
  "session_id_hash",
  "protocol_hash",
  "prompt_version",
  "screen_id",
] as const;

/** Every tag key that can ever reach the tracker — the two lists joined and
 * nothing else. */
export const ALLOWED_TAG_KEYS: readonly string[] = [...IDENTITY_TAG_KEYS, ...EVENT_TAG_KEYS];

/** One shape per key. A value that does not match is dropped, not repaired:
 * a half-scrubbed identifier is still an identifier. */
const TAG_SHAPES: Readonly<Record<string, RegExp>> = {
  app_version: /^\d{1,4}\.\d{1,4}\.\d{1,4}(?:-[A-Za-z0-9.]{1,32})?$/,
  build_id: /^[A-Za-z][A-Za-z0-9._-]{0,63}$/,
  sbom_digest: /^sha256:[0-9a-f]{64}$/,
  environment: /^(?:dev|staging|prod)$/,
  release_channel: /^[a-z][a-z0-9-]{0,31}$/,
  platform: /^(?:ios|android|web)$/,
  os_version: /^\d{1,3}(?:\.\d{1,4}){0,2}$/,
  device_model: /^[A-Za-z][A-Za-z0-9,._-]{0,39}$/,
  tenant_id: /^[a-z][a-z0-9-]{0,63}$/,
  session_id_hash: /^[0-9a-f]{16,64}$/,
  protocol_hash: /^[0-9a-f]{64}$/,
  prompt_version: /^v\d{1,4}(?:\.\d{1,4}){0,2}$/,
  screen_id: /^[a-z][a-z0-9_]{1,39}$/,
};

/** The closed set of breadcrumb categories. An entry outside it is dropped
 * whole rather than kept without its category. */
export const BREADCRUMB_CATEGORIES = ["lifecycle", "navigation", "network", "permission"] as const;
export type BreadcrumbCategory = (typeof BREADCRUMB_CATEGORIES)[number];

const ERROR_CODE = /^[a-z][a-z0-9_]{2,63}$/;
const EXCEPTION_TYPE = /^[A-Za-z_$][A-Za-z0-9_$]{0,63}$/;
/** A module path must contain a letter, which is what stops a bare digit run
 * (a phone number, a national id) from passing as one. */
const FRAME_MODULE = /^(?=.*[A-Za-z])[A-Za-z0-9_@][A-Za-z0-9_./@-]{0,119}$/;
const FRAME_FUNCTION = /^[A-Za-z_$][A-Za-z0-9_$.<>]{0,79}$/;
const BREADCRUMB_EVENT = /^[a-z][a-z0-9_]{1,39}$/;
/**
 * A ROUTE TEMPLATE, never a URL. Each segment is either a lowercase literal or
 * a `{param}` slot, so a path carrying a real id — `/records/10000000146` —
 * cannot match, and neither can anything with a host, a query or a fragment.
 */
const ROUTE_TEMPLATE = /^(?:\/(?:[a-z][a-z0-9-]*|\{[A-Za-z][A-Za-z0-9]*\}))+\/?$/;

export type TelemetryPlatform = "ios" | "android" | "web";
export type TelemetryEnvironment = "dev" | "staging" | "prod";

/** Build metadata, fixed for the life of the process. */
export interface TelemetryIdentity {
  readonly appVersion: string;
  readonly buildId: string;
  readonly sbomDigest: string;
  readonly platform: TelemetryPlatform;
  readonly osVersion: string;
  readonly deviceModel: string;
  readonly environment: TelemetryEnvironment;
  readonly releaseChannel: string;
  readonly tenantId: string;
}

/** Four code coordinates. There is no room here for a local or a source line. */
export interface CrashFrame {
  readonly module: string;
  readonly function: string;
  readonly lineno?: number;
  readonly colno?: number;
}

/** A category, an event code, and — where the category is network — a route
 * template and an HTTP status. No message, no data bag, no URL. */
export interface CrashBreadcrumb {
  readonly category: BreadcrumbCategory;
  readonly event: string;
  readonly route?: string;
  readonly status?: number;
}

/** Everything that may leave the device about one crash. */
export interface CrashReport {
  readonly errorCode: string;
  readonly fingerprint: string;
  readonly exceptionType: string | null;
  readonly frames: readonly CrashFrame[];
  readonly breadcrumbs: readonly CrashBreadcrumb[];
  readonly tags: Readonly<Record<string, string>>;
  readonly timestampMs: number;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

/**
 * The longest string any shape below can accept. Checked BEFORE the regex, so
 * no pattern is ever run against an unbounded input — the shapes have nested
 * quantifiers (a route template is a repeat of segments), and a crash reporter
 * that can be made to spin on a long string is a denial of service triggered
 * by the very condition it exists to report.
 */
const MAX_READ_CHARS = 256;

/** Read one string under `key`, keeping it only if it matches `shape`. */
function readString(source: unknown, key: string, shape: RegExp): string | null {
  const record = asRecord(source);
  const value = record?.[key];
  if (typeof value !== "string" || value.length > MAX_READ_CHARS) {
    return null;
  }
  return shape.test(value) ? value : null;
}

/** Read one finite number under `key` within an inclusive range. */
function readNumber(source: unknown, key: string, min: number, max: number): number | null {
  const record = asRecord(source);
  const value = record?.[key];
  if (typeof value !== "number" || !Number.isFinite(value) || value < min || value > max) {
    return null;
  }
  return value;
}

function readArray(source: unknown, key: string): unknown[] {
  const value = asRecord(source)?.[key];
  return Array.isArray(value) ? value : [];
}

function readRecord(source: unknown, key: string): Record<string, unknown> | null {
  return asRecord(asRecord(source)?.[key]);
}

function isBreadcrumbCategory(value: string): value is BreadcrumbCategory {
  return (BREADCRUMB_CATEGORIES as readonly string[]).includes(value);
}

/** Tags the crash event itself may set, each under its own shape. */
function eventTags(raw: unknown): Record<string, string> {
  const source = readRecord(raw, "tags");
  const tags: Record<string, string> = {};
  for (const key of EVENT_TAG_KEYS) {
    const value = readString(source, key, TAG_SHAPES[key]);
    if (value !== null) {
      tags[key] = value;
    }
  }
  return tags;
}

/** Tags from the app's own build metadata. A field failing its shape is
 * omitted; a wrong app version is not worth an unshaped string on the wire. */
function identityTags(identity: TelemetryIdentity): Record<string, string> {
  const supplied: Record<string, string> = {
    app_version: identity.appVersion,
    build_id: identity.buildId,
    sbom_digest: identity.sbomDigest,
    environment: identity.environment,
    release_channel: identity.releaseChannel,
    platform: identity.platform,
    os_version: identity.osVersion,
    device_model: identity.deviceModel,
    tenant_id: identity.tenantId,
  };
  const tags: Record<string, string> = {};
  for (const key of IDENTITY_TAG_KEYS) {
    const value = supplied[key];
    if (typeof value === "string" && TAG_SHAPES[key].test(value)) {
      tags[key] = value;
    }
  }
  return tags;
}

function scrubFrames(exceptionValue: unknown): CrashFrame[] {
  const stacktrace = readRecord(exceptionValue, "stacktrace");
  const frames: CrashFrame[] = [];
  for (const candidate of readArray(stacktrace, "frames")) {
    const module = readString(candidate, "module", FRAME_MODULE);
    const fn = readString(candidate, "function", FRAME_FUNCTION);
    if (module === null || fn === null) {
      // A frame we cannot describe in code coordinates is dropped whole. A
      // partial frame is not worth the risk of the half we could not shape.
      continue;
    }
    const lineno = readNumber(candidate, "lineno", 0, 10_000_000);
    const colno = readNumber(candidate, "colno", 0, 10_000_000);
    frames.push({
      module,
      function: fn,
      ...(lineno === null ? {} : { lineno }),
      ...(colno === null ? {} : { colno }),
    });
  }
  return frames;
}

function scrubBreadcrumbs(raw: unknown): CrashBreadcrumb[] {
  const source = readRecord(raw, "breadcrumbs");
  const crumbs: CrashBreadcrumb[] = [];
  for (const candidate of readArray(source, "values")) {
    const category = readString(candidate, "category", /^[a-z_]{1,32}$/);
    const event = readString(candidate, "event", BREADCRUMB_EVENT);
    if (category === null || event === null || !isBreadcrumbCategory(category)) {
      continue;
    }
    const route = readString(candidate, "route", ROUTE_TEMPLATE);
    const status = readNumber(candidate, "status", 100, 599);
    crumbs.push({
      category,
      event,
      ...(route === null ? {} : { route }),
      ...(status === null ? {} : { status }),
    });
  }
  return crumbs;
}

/**
 * A grouping key over allow-listed fields ONLY.
 *
 * This is deliberate rather than incidental. A fingerprint derived from the
 * exception message would be a hash of patient text, and a hash of a short
 * identifier — a phone number has ten million candidates — is not a
 * de-identification, it is a lookup table. So the digest is taken over the
 * error code and the frames, all of which have already passed their shapes.
 */
function fingerprint(
  errorCode: string,
  exceptionType: string | null,
  frames: CrashFrame[],
): string {
  const material = [
    errorCode,
    exceptionType ?? "",
    ...frames.map((frame) => `${frame.module}:${frame.function}:${frame.lineno ?? ""}`),
  ].join("|");
  return bytesToHex(sha256(new TextEncoder().encode(material))).slice(0, 16);
}

function bytesToHex(bytes: Uint8Array): string {
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

/**
 * Build the only object that may be sent about a crash.
 *
 * `raw` is `unknown` on purpose: it is whatever the runtime handed us, and the
 * type system must not let a future caller spread it into the result.
 */
export function buildCrashReport(identity: TelemetryIdentity, raw: unknown): CrashReport {
  const exception = readRecord(raw, "exception");
  const first = readArray(exception, "values")[0] ?? null;
  const exceptionType = readString(first, "type", EXCEPTION_TYPE);
  const frames = scrubFrames(first);
  const errorCode = readString(raw, "errorCode", ERROR_CODE) ?? UNCLASSIFIED_ERROR_CODE;
  return {
    errorCode,
    fingerprint: fingerprint(errorCode, exceptionType, frames),
    exceptionType,
    frames,
    breadcrumbs: scrubBreadcrumbs(raw),
    tags: { ...identityTags(identity), ...eventTags(raw) },
    timestampMs: readNumber(raw, "timestampMs", 0, Number.MAX_SAFE_INTEGER) ?? 0,
  };
}
