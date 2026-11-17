/**
 * The console's own liveness endpoint (files/08 §7 table: "Admin console —
 * `/healthz` + CSP header assertion"). Alive means the Next server answers;
 * it reveals nothing about the API or any source behind it.
 */
export const dynamic = "force-dynamic";

export function GET(): Response {
  return Response.json({ status: "alive" }, { headers: { "cache-control": "no-store" } });
}
