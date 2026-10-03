/**
 * INT-351 — the console's Content-Security-Policy (files/08 §0c F14; the
 * admin-console row's nonce CSP, invariant 48).
 *
 * Nonce-based and `strict-dynamic`: only scripts carrying this request's nonce
 * run, and Next.js applies the nonce to its own scripts when it finds it in
 * the request's CSP header (the App Router's documented mechanism). No
 * `unsafe-inline` anywhere, no `unsafe-eval` in production — React's
 * development build needs `eval` for its error overlay, so development alone
 * gets it. No `frame-src` beyond `'none'`: the iframe pattern is deleted (F1),
 * and nothing may frame the console (`frame-ancestors 'none'`).
 *
 * INT-459 — one inline style is admitted, by its hash, and only as an
 * attribute. Under the route-level loading state (app/loading.tsx) every page
 * streams, and React parks a segment that finishes late inside an SVG (a
 * chart) in `<svg aria-hidden="true" style="display:none">` until its script
 * moves it into place. A hash admits an attribute only beside
 * `'unsafe-hashes'`, so `style-src-attr` carries that keyword and the one
 * hash, and nothing else. Every other inline style, and a `<style>` element
 * with the same text, is still refused (owner decision, 3 Oct 2026; pinned in
 * e2e/states.spec.ts, which derives the value from React's streamed markup).
 */
import { createHash } from "node:crypto";

const NONCE = /^[A-Za-z0-9+/]{6,}={0,2}$/;

/** The style React's streaming renderer writes on a parked SVG segment. */
export const STREAMED_SEGMENT_STYLE = "display:none";

function hashSource(value: string): string {
  return `'sha256-${createHash("sha256").update(value, "utf8").digest("base64")}'`;
}

const STYLE_ATTRIBUTES = `style-src-attr 'unsafe-hashes' ${hashSource(STREAMED_SEGMENT_STYLE)}`;

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
    STYLE_ATTRIBUTES,
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
