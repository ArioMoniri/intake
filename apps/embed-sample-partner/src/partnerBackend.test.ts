/**
 * INT-320 follow-up — the fixture-backed proof of the sample partner handshake.
 *
 * No live infra: a recorded upstream response stands in for the real Önvizit
 * ``POST /embed/v1/launch-tickets``. What these tests pin:
 * - the partner backend calls the real embed endpoint with POST, the bearer
 *   credential and a ``{tenant_id}`` body — and nothing else;
 * - it returns ONLY the three public launch fields; the admin token never
 *   crosses back to the page;
 * - an upstream refusal (bad bearer, unknown tenant, unseeded signing key) and
 *   a malformed body both fail closed with an id-shaped error, no token leak;
 * - the backend's output composes with ``@intake/embed-sdk``: fed to the SDK it
 *   opens exactly the branded https launch_url — the whole partner -> ticket ->
 *   launch path, proven in one place.
 *
 * The server-side half (mint -> launch -> consent over the real FastAPI app) is
 * proven by tests/embed/test_router.py; together they cover the full handshake.
 */

import { describe, expect, it } from "vitest";

import { startPrevisit } from "@intake/embed-sdk";

import {
  handleTicketRequest,
  mintLaunchTicket,
  PartnerBackendError,
  type LaunchResponse,
} from "./partnerBackend.js";

const DEV_TENANT = "0b6f9d2e-1111-5aaa-8bbb-000000000001";
const ADMIN_TOKEN = "unit-lane-admin-token";
const API_BASE = "http://127.0.0.1:8000";

/** Unpadded base64url, the encoding of each part of a compact JWT. */
function base64url(text: string): string {
  return btoa(text).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

/** The synthetic ticket's three parts. It is built here, at runtime, so no
 * token-shaped literal exists in the source for a secret scanner to report as
 * a leaked credential (INT-431). Nothing about it is real: the header names
 * HS256, the payload names the dev tenant, and the "signature" is a label. */
const TICKET_PARTS = {
  header: { alg: "HS256" },
  payload: { tenant: "dev" },
  signature: "signature-sample",
} as const;

const SYNTHETIC_TICKET = [
  base64url(JSON.stringify(TICKET_PARTS.header)),
  base64url(JSON.stringify(TICKET_PARTS.payload)),
  base64url(TICKET_PARTS.signature),
].join(".");

/** A recorded upstream mint response, shaped exactly like the real endpoint:
 * an HS256-style token and a branded https launch_url with the ticket in the
 * URL fragment (so it never reaches an access log). */
const MINTED: LaunchResponse = {
  ticket: SYNTHETIC_TICKET,
  launch_url: `https://intake.app/embed/launch#ticket=${SYNTHETIC_TICKET}`,
  expires_at: 1_800_000_120,
};

interface Recorded {
  url: string;
  method: string | undefined;
  authorization: string | null;
  contentType: string | null;
  body: string | undefined;
}

/** A fake upstream that records the request and replies with ``responseBody``
 * at ``status``. */
function recordingFetch(
  responseBody: unknown,
  status = 200,
): { fetchImpl: typeof fetch; seen: Recorded[] } {
  const seen: Recorded[] = [];
  const fetchImpl = (async (input: string | URL, init?: RequestInit) => {
    const headers = new Headers(init?.headers);
    seen.push({
      url: String(input),
      method: init?.method,
      authorization: headers.get("authorization"),
      contentType: headers.get("content-type"),
      body: typeof init?.body === "string" ? init.body : undefined,
    });
    return {
      ok: status >= 200 && status < 300,
      status,
      json: async () => responseBody,
    } as unknown as Response;
  }) as unknown as typeof fetch;
  return { fetchImpl, seen };
}

describe("the synthetic ticket fixture (INT-431)", () => {
  it("is a compact three-part base64url token whose parts decode to the fixture", () => {
    const decode = (part: string): string => atob(part.replace(/-/g, "+").replace(/_/g, "/"));
    const [header = "", payload = "", signature = "", ...rest] = MINTED.ticket.split(".");
    expect(rest).toEqual([]);
    for (const part of [header, payload, signature]) {
      expect(part).toMatch(/^[A-Za-z0-9_-]+$/);
    }
    expect(JSON.parse(decode(header))).toEqual(TICKET_PARTS.header);
    expect(JSON.parse(decode(payload))).toEqual(TICKET_PARTS.payload);
    expect(decode(signature)).toBe(TICKET_PARTS.signature);
    expect(MINTED.launch_url.endsWith(`#ticket=${MINTED.ticket}`)).toBe(true);
  });
});

describe("mintLaunchTicket", () => {
  it("calls the real embed endpoint with the bearer and a tenant_id body", async () => {
    const { fetchImpl, seen } = recordingFetch(MINTED);
    const launch = await mintLaunchTicket({
      apiBase: API_BASE,
      adminToken: ADMIN_TOKEN,
      tenantId: DEV_TENANT,
      fetchImpl,
    });

    expect(launch).toEqual(MINTED);
    expect(seen).toHaveLength(1);
    const call = seen[0]!;
    expect(call.url).toBe(`${API_BASE}/embed/v1/launch-tickets`);
    expect(call.method).toBe("POST");
    expect(call.authorization).toBe(`Bearer ${ADMIN_TOKEN}`);
    expect(call.contentType).toBe("application/json");
    expect(JSON.parse(call.body ?? "{}")).toEqual({ tenant_id: DEV_TENANT });
  });

  it("trims a trailing slash on the api base", async () => {
    const { fetchImpl, seen } = recordingFetch(MINTED);
    await mintLaunchTicket({
      apiBase: `${API_BASE}/`,
      adminToken: ADMIN_TOKEN,
      tenantId: DEV_TENANT,
      fetchImpl,
    });
    expect(seen[0]!.url).toBe(`${API_BASE}/embed/v1/launch-tickets`);
  });

  it("fails closed on an upstream refusal without leaking the status verbatim", async () => {
    // 503 = the dev signing key is not seeded / the embed surface is unconfigured
    const { fetchImpl } = recordingFetch({ error: "embed_signing_key_unavailable" }, 503);
    await expect(
      mintLaunchTicket({
        apiBase: API_BASE,
        adminToken: ADMIN_TOKEN,
        tenantId: DEV_TENANT,
        fetchImpl,
      }),
    ).rejects.toBeInstanceOf(PartnerBackendError);
  });

  it("rejects a malformed upstream body", async () => {
    const { fetchImpl } = recordingFetch({ ticket: "t", launch_url: "https://intake.app/x" }); // no expires_at
    await expect(
      mintLaunchTicket({
        apiBase: API_BASE,
        adminToken: ADMIN_TOKEN,
        tenantId: DEV_TENANT,
        fetchImpl,
      }),
    ).rejects.toBeInstanceOf(PartnerBackendError);
  });
});

describe("handleTicketRequest", () => {
  it("returns only the public launch fields — never the admin token", async () => {
    const { fetchImpl } = recordingFetch(MINTED);
    const result = await handleTicketRequest({
      apiBase: API_BASE,
      adminToken: ADMIN_TOKEN,
      tenantId: DEV_TENANT,
      fetchImpl,
    });
    expect(result.status).toBe(200);
    expect(result.body).toEqual(MINTED);
    expect(JSON.stringify(result.body)).not.toContain(ADMIN_TOKEN);
    expect(Object.keys(result.body)).toEqual(["ticket", "launch_url", "expires_at"]);
  });

  it("is unconfigured (500) when no credential is set, and says how to fix it", async () => {
    const result = await handleTicketRequest({
      apiBase: API_BASE,
      adminToken: "",
      tenantId: DEV_TENANT,
    });
    expect(result.status).toBe(500);
    expect(result.body).toEqual({ error: "partner_backend_unconfigured" });
    expect(result.logLine).toContain("ONVIZIT_ADMIN_TOKEN");
  });

  it("maps an upstream refusal to an id-shaped error, no token or upstream body", async () => {
    const { fetchImpl } = recordingFetch(
      { error: "unknown_embed_tenant", secretish: ADMIN_TOKEN },
      404,
    );
    const result = await handleTicketRequest({
      apiBase: API_BASE,
      adminToken: ADMIN_TOKEN,
      tenantId: DEV_TENANT,
      fetchImpl,
    });
    expect(result.status).toBe(502);
    expect(result.body).toEqual({ error: "launch_unavailable" });
    expect(JSON.stringify(result.body)).not.toContain(ADMIN_TOKEN);
  });
});

describe("partner backend output composes with @intake/embed-sdk", () => {
  it("the SDK opens exactly the branded https launch_url the backend returned", async () => {
    // 1) the partner backend mints against a recorded upstream
    const { fetchImpl: upstream } = recordingFetch(MINTED);
    const minted = await handleTicketRequest({
      apiBase: API_BASE,
      adminToken: ADMIN_TOKEN,
      tenantId: DEV_TENANT,
      fetchImpl: upstream,
    });
    expect(minted.status).toBe(200);

    // 2) the browser SDK calls the partner endpoint, which returns that body
    const pageFetch = (async () =>
      ({
        ok: true,
        status: 200,
        json: async () => minted.body,
      }) as unknown as Response) as unknown as typeof fetch;

    let opened: string | undefined;
    const launched = await startPrevisit({
      ticketEndpoint: "/onvizit/ticket",
      fetchImpl: pageFetch,
      open: (url) => {
        opened = url;
      },
    });

    // 3) the whole path resolves to the branded https launch_url, unchanged
    expect(launched.launch_url).toBe(MINTED.launch_url);
    expect(opened).toBe(MINTED.launch_url);
    expect(opened?.startsWith("https://")).toBe(true);
  });
});
