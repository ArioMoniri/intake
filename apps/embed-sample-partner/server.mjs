// INT-320 follow-up — the runnable sample partner server (ADR-029).
//
// A tiny, dependency-free Node server (stdlib http + global fetch) that:
//   - serves the synthetic partner page and its compiled browser assets, and
//   - exposes POST /onvizit/ticket, which mints a launch ticket server-to-server
//     via the real Önvizit embed endpoint using handleTicketRequest().
//
// It imports the SAME typed module the vitest proof exercises (dist/, built by
// `pnpm run build`). The Önvizit credential lives only here; it never reaches
// the browser. Docker is not required — run it with a bare `node`.
//
// Config (env):
//   PARTNER_PORT         default 4123
//   ONVIZIT_API_BASE     default http://127.0.0.1:8000  (the dev Önvizit API)
//   ONVIZIT_ADMIN_TOKEN  the dev admin bearer (INTAKE_DEV_TOKEN_ADMIN) — required
//                        for a live mint; without it /onvizit/ticket returns 500
//   EMBED_TENANT_ID      default the synthetic dev-partner-alpha row

import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

import { handleTicketRequest } from "./dist/partnerBackend.js";

const PORT = Number(process.env.PARTNER_PORT ?? "4123");
const API_BASE = process.env.ONVIZIT_API_BASE ?? "http://127.0.0.1:8000";
const ADMIN_TOKEN = process.env.ONVIZIT_ADMIN_TOKEN ?? "";
const TENANT_ID = process.env.EMBED_TENANT_ID ?? "0b6f9d2e-1111-5aaa-8bbb-000000000001";

// The one route the partner page calls (src/browser/main.ts TICKET_ENDPOINT).
const TICKET_ROUTE = "/onvizit/ticket";

// A fixed route -> file map. Only these paths are served, so there is no path
// traversal surface (invariant: sanitize file paths).
const STATIC = {
  "/": { file: "public/index.html", type: "text/html; charset=utf-8" },
  "/styles.css": { file: "public/styles.css", type: "text/css; charset=utf-8" },
  "/web/main.js": { file: "dist/web/main.js", type: "text/javascript; charset=utf-8" },
  "/web/vendor/index.js": {
    file: "dist/web/vendor/index.js",
    type: "text/javascript; charset=utf-8",
  },
};

function resolve(relative) {
  return fileURLToPath(new URL(relative, import.meta.url));
}

async function serveStatic(res, entry) {
  try {
    const body = await readFile(resolve(entry.file));
    res.writeHead(200, { "content-type": entry.type });
    res.end(body);
  } catch {
    res.writeHead(500, { "content-type": "application/json" });
    res.end(
      JSON.stringify({
        error: "asset_missing",
        hint: `run \`pnpm --filter @intake/embed-sample-partner build\` first (${entry.file})`,
      }),
    );
  }
}

function sendJson(res, status, body) {
  res.writeHead(status, { "content-type": "application/json" });
  res.end(JSON.stringify(body));
}

async function mintTicket(res) {
  const result = await handleTicketRequest({
    apiBase: API_BASE,
    adminToken: ADMIN_TOKEN,
    tenantId: TENANT_ID,
  });
  // The reason stays server-side for the operator; the browser gets body only.
  console.log(`[${TICKET_ROUTE}] ${result.status} — ${result.logLine}`);
  sendJson(res, result.status, result.body);
}

const server = createServer((req, res) => {
  const url = new URL(req.url ?? "/", `http://localhost:${PORT}`);
  const path = url.pathname;

  if (req.method === "POST" && path === TICKET_ROUTE) {
    void mintTicket(res);
    return;
  }
  if (req.method === "GET" && Object.prototype.hasOwnProperty.call(STATIC, path)) {
    void serveStatic(res, STATIC[path]);
    return;
  }
  if (path === TICKET_ROUTE) {
    sendJson(res, 405, { error: "method_not_allowed" });
    return;
  }
  sendJson(res, 404, { error: "not_found" });
});

server.listen(PORT, () => {
  console.log(`Sample partner app on http://localhost:${PORT}`);
  console.log(`  minting tenant ${TENANT_ID} via ${API_BASE}/embed/v1/launch-tickets`);
  if (ADMIN_TOKEN.length === 0) {
    console.log(
      "  ONVIZIT_ADMIN_TOKEN is not set — the page loads, but a tap returns 500 " +
        "until you set it to the dev admin bearer (INTAKE_DEV_TOKEN_ADMIN).",
    );
  }
});
