/**
 * INT-351 — the console's Content-Security-Policy (files/08 §0c F14; the
 * admin-console row's "nonce CSP with no `unsafe-*`", invariant 48).
 *
 * Nonce-based and `strict-dynamic`: only scripts carrying this request's nonce
 * run, and Next.js applies the nonce to its own scripts when it finds it in
 * the request's CSP header (the App Router's documented mechanism). No
 * `unsafe-inline`, no `unsafe-eval` in production — React's development build
 * needs `eval` for its error overlay, so development alone gets it. No
 * `frame-src` beyond `'none'`: the iframe pattern is deleted (F1), and nothing
 * may frame the console (`frame-ancestors 'none'`).
 *
 * INT-563 (ADR-043): `form-action` admits one origin beside `'self'` — the
 * Keycloak origin of the four-eyes step-up, when one is configured — because
 * the **Onayla** form's 303 continues to Keycloak's authorization endpoint and
 * browsers hold a form's redirects to `form-action`. Nothing else widens, and
 * with no origin configured the directive stays `'self'`.
 */

const NONCE = /^[A-Za-z0-9+/]{6,}={0,2}$/;
/** An origin and nothing else: scheme, host, optional port. */
const ORIGIN = /^https?:\/\/(?:[a-z0-9.-]+|\[::1\])(?::[0-9]{1,5})?$/;

export function buildCsp(nonce: string, mode: string, stepUpOrigin: string | null = null): string {
  if (!NONCE.test(nonce)) {
    throw new Error("the CSP nonce must be base64");
  }
  if (stepUpOrigin !== null && !ORIGIN.test(stepUpOrigin)) {
    throw new Error("the step-up origin must be a bare origin");
  }
  const forms = stepUpOrigin === null ? `'self'` : `'self' ${stepUpOrigin}`;
  const scripts = [`'self'`, `'nonce-${nonce}'`, `'strict-dynamic'`];
  if (mode === "development") scripts.push(`'unsafe-eval'`);
  return [
    `default-src 'self'`,
    `script-src ${scripts.join(" ")}`,
    `style-src 'self' 'nonce-${nonce}'`,
    `img-src 'self'`,
    `font-src 'self'`,
    `connect-src 'self'`,
    `object-src 'none'`,
    `frame-src 'none'`,
    `frame-ancestors 'none'`,
    `base-uri 'none'`,
    `form-action ${forms}`,
  ].join("; ");
}

/** A fresh per-request nonce: 16 random bytes, base64. */
export function newNonce(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}
