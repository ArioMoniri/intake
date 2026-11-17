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
 */

const NONCE = /^[A-Za-z0-9+/]{6,}={0,2}$/;

export function buildCsp(nonce: string, mode: string): string {
  if (!NONCE.test(nonce)) {
    throw new Error("the CSP nonce must be base64");
  }
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
    `form-action 'self'`,
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
