/**
 * The one API-base resolver (INT-328, audit F01). Pure and node-testable: the
 * `expo-constants` reading and the dev LAN walk are handed in by
 * expoApiBase.ts, so nothing here can reach lib/dev.
 *
 * A release build (`!__DEV__`) talks to exactly one base: the one configured
 * at build time (`extra.apiBaseUrl`, filled by app.config.ts from the EAS
 * variable `EXPO_PUBLIC_API_BASE_URL`). It must be https on a public DNS name.
 * Anything else — unset, http, malformed, loopback, a LAN address — is a typed
 * `ApiBaseUnconfigured`, never a guess: the production FQDN is a human
 * decision (HB-I14), and a build without it fails closed with its own copy
 * rather than the "server unreachable" line that blames the patient's signal.
 *
 * A dev build walks the Metro hostUri and `extra.asrHosts` exactly as it
 * always has; the configured base is not consulted there.
 */
import { AuthApiError } from "./errors";

/** Why a release build has no usable base. The UI shows one line for all four;
 * the reason is for tests and the operator, and never carries the value. */
export type ApiBaseRefusal = "unset" | "insecure" | "malformed" | "not_public";

export class ApiBaseUnconfigured extends AuthApiError {
  readonly reason: ApiBaseRefusal;

  constructor(reason: ApiBaseRefusal) {
    super("unconfigured");
    this.reason = reason;
  }
}

const SCHEME = /^([A-Za-z][A-Za-z0-9+.-]*):\/\//;
/** Userinfo, query, fragment, whitespace: none belongs in a base. */
const FORBIDDEN = /[?#@\s\\]/;
const AUTHORITY = /^([^:]+)(?::(\d{1,5}))?$/;
const DNS_NAME =
  /^(?=.{1,253}$)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*$/;
/** Special-use names that never resolve to a public service (RFC 6761,
 * RFC 6762, RFC 8375, and ICANN's private-use `internal`). */
const LOCAL_SUFFIX = /(?:^|\.)(?:localhost|local|home\.arpa|internal)$/;

/**
 * The release base, normalised (lower-case host, no trailing slash), or an
 * `ApiBaseUnconfigured` naming why not.
 */
export function parseReleaseApiBase(raw: unknown): string {
  if (typeof raw !== "string" || raw.trim() === "") {
    throw new ApiBaseUnconfigured("unset");
  }
  const value = raw.trim();
  const scheme = SCHEME.exec(value);
  if (scheme === null) {
    throw new ApiBaseUnconfigured("malformed");
  }
  if (scheme[1].toLowerCase() !== "https") {
    throw new ApiBaseUnconfigured("insecure");
  }
  const rest = value.slice(scheme[0].length);
  if (FORBIDDEN.test(rest)) {
    throw new ApiBaseUnconfigured("malformed");
  }
  const slash = rest.indexOf("/");
  const authority = slash === -1 ? rest : rest.slice(0, slash);
  const path = slash === -1 ? "" : rest.slice(slash).replace(/\/+$/, "");
  if (authority.startsWith("[")) {
    throw new ApiBaseUnconfigured("not_public"); // an IPv6 literal
  }
  const parts = AUTHORITY.exec(authority);
  if (parts === null) {
    throw new ApiBaseUnconfigured("malformed");
  }
  const host = parts[1].toLowerCase();
  const port = parts[2];
  if (port !== undefined && (Number(port) < 1 || Number(port) > 65535)) {
    throw new ApiBaseUnconfigured("malformed");
  }
  if (!DNS_NAME.test(host)) {
    throw new ApiBaseUnconfigured("malformed");
  }
  const topLabel = host.slice(host.lastIndexOf(".") + 1);
  // a single label is a LAN name; a numeric top label is an IPv4 literal
  if (!host.includes(".") || /^\d+$/.test(topLabel) || LOCAL_SUFFIX.test(host)) {
    throw new ApiBaseUnconfigured("not_public");
  }
  return `https://${host}${port === undefined ? "" : `:${port}`}${path}`;
}

export interface ApiBaseSources {
  /** `__DEV__`, passed in so the rule is testable in node. */
  readonly isDev: boolean;
  /** `extra.apiBaseUrl` as the build carries it — unvalidated. */
  readonly configured: unknown;
  /** The dev LAN walk: first base whose /healthz answers, or null. Called
   * only when `isDev`; a release build never reaches it. */
  readonly devBase: () => Promise<string | null>;
}

/**
 * Release: the configured https base, or `ApiBaseUnconfigured`.
 * Dev: whatever the LAN walk finds, null included, so each caller keeps its
 * own miss (the auth client throws `network`, the dev clip source goes quiet).
 */
export async function resolveApiBase(sources: ApiBaseSources): Promise<string | null> {
  if (!sources.isDev) {
    return parseReleaseApiBase(sources.configured);
  }
  return sources.devBase();
}
