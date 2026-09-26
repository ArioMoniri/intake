/**
 * INT-351 — who may see the ops console, and where its data comes from.
 *
 * **Admission is the API's, not this server's.** The page forwards the
 * caller's bearer to `GET /admin/ops`, where the INT-180 gate decides: the
 * OIDC verifier (issuer, audience and a mirrored JWKS — 503 for everyone
 * while any of the three is unset), the files/08 §2.3 IP allow-list (HB-A16:
 * it ships empty and an empty list admits nobody), the role matrix (the
 * platform-scope roles) and the audit wrapper. One gate, already tested,
 * rather than a second verifier here that could disagree with it on the day
 * it matters.
 *
 * What this module owns is the two inputs to that call, and both fail closed:
 * no configured API base means no call at all, and a header that is not
 * exactly `Bearer <one token>` is not forwarded.
 */

/** Where the admin API lives. A plain http(s) origin; nothing else. */
export interface OpsConfig {
  apiBase: string;
}

export const ENV_API_BASE = "INTAKE_ADMIN_API_BASE";

const TOKEN = /^[A-Za-z0-9._~+/=-]{1,8192}$/;

/**
 * The configured API origin, or `null` — never a default. A URL with
 * credentials, a path beyond `/`, a query or a fragment is refused: the
 * console names an origin, and anything more is somewhere a tenant or a
 * datasource could be smuggled in (files/08 §0b F1, §0c F9).
 */
export function opsConfigFromEnv(env: Record<string, string | undefined>): OpsConfig | null {
  const raw = env[ENV_API_BASE]?.trim();
  if (!raw) return null;
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    return null;
  }
  if (url.protocol !== "https:" && url.protocol !== "http:") return null;
  if (url.username || url.password || url.search || url.hash) return null;
  if (url.pathname !== "/" && url.pathname !== "") return null;
  return { apiBase: url.origin };
}

/** The caller's `Authorization` header, only when it is one bearer token. */
export function bearerFrom(headers: Headers): string | null {
  const value = headers.get("authorization");
  if (value === null) return null;
  const match = /^Bearer (\S+)$/.exec(value);
  if (match === null || !TOKEN.test(match[1]!)) return null;
  return `Bearer ${match[1]}`;
}
