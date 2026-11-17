/**
 * INT-351 — the per-request CSP (files/08 §0c F14; admin-console row,
 * invariant 48). Next.js 16 calls this file `proxy` (it was `middleware`).
 *
 * A fresh nonce per request goes into the request's CSP header — which is
 * where Next.js reads it from to stamp its own scripts — and into the
 * response's. Production carries no `unsafe-*`; see `src/ops/csp.ts`. Also:
 * no referrer leaves the console, and nothing may frame or sniff it.
 */
import { NextResponse, type NextRequest } from "next/server";

import { buildCsp, newNonce } from "./src/ops/csp";

export function proxy(request: NextRequest): NextResponse {
  const nonce = newNonce();
  const csp = buildCsp(nonce, process.env.NODE_ENV ?? "production");
  const forwarded = new Headers(request.headers);
  forwarded.set("x-nonce", nonce);
  forwarded.set("content-security-policy", csp);
  const response = NextResponse.next({ request: { headers: forwarded } });
  response.headers.set("content-security-policy", csp);
  response.headers.set("referrer-policy", "no-referrer");
  response.headers.set("x-content-type-options", "nosniff");
  response.headers.set("x-frame-options", "DENY");
  response.headers.set("cache-control", "no-store");
  return response;
}

export const config = {
  matcher: [
    {
      source: "/((?!_next/static|_next/image|favicon.ico).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
