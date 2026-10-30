/**
 * INT-459 — an address that is not a console page: an empty state with one
 * way back to the overview (src/ui/states.tsx).
 *
 * Rendered per request, not prerendered: a prerendered 404 is built before any
 * request exists, so its scripts carry no CSP nonce and the policy blocks them
 * (proxy.ts stamps a fresh nonce on every response). `connection()` opts the
 * file into request-time rendering, where Next.js reads the nonce.
 */
import { connection } from "next/server";
import type { ReactElement } from "react";

import { NotFoundView } from "../src/ui/states";

export default async function NotFound(): Promise<ReactElement> {
  await connection();
  return <NotFoundView />;
}
