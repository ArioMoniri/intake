/**
 * INT-563 (ADR-043) — the console's half of the four-eyes step-up.
 *
 * The admin API is a recording fetch here (no server, no Keycloak): each test
 * drives `beginStepUp` or `completeStepUp` the way the two routes do and reads
 * what was sent and where the browser goes. Most of the file is near misses —
 * the honest sequence with one thing changed — because the console's job is
 * to refuse: a cross-site post, an authorization URL that is not Keycloak's
 * step-up endpoint (the console is not an open redirect), a grant or action
 * the API did not shape, an action no approve route belongs to.
 */
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { buildCsp } from "../src/ops/csp";
import { APPROVALS, approvalFor } from "../src/step-up/approvals";
import { COPY } from "../src/step-up/copy";
import {
  beginStepUp,
  checkedAuthorizeUrl,
  completeStepUp,
  stepUpOriginFromEnv,
} from "../src/step-up/flow";
import { StepUpPage } from "../src/step-up/form";
import { STEP_UP_RESULTS, apiResult, stepUpResultFrom } from "../src/step-up/results";
import { RETURN_COOKIE, destination, returnCookie, returnFrom } from "../src/step-up/return";
import { AXE_TIMEOUT_MS, documentFor, violations } from "./support/axe";

const API = { apiBase: "http://api:8000" };
const ORIGIN = "https://auth.staging.example.test";
const BEARER = "Bearer kc-access-token";
const ACTION = "0123456789abcdef0123456789abcdef";
const GRANT = `sug_${"a".repeat(32)}`;
const STATE = "aB3_-cD4eF5gH6iJ7kL8mN9oP0qR1sT2";

function authorizeUrl(changes: Record<string, string | null> = {}, base = ORIGIN): string {
  const url = new URL(`${base}/realms/intake/protocol/openid-connect/auth`);
  const params: Record<string, string | null> = {
    client_id: "admin-web-stepup",
    response_type: "code",
    scope: "openid",
    redirect_uri: "https://admin.staging.example.test/step-up/callback",
    state: STATE,
    nonce: "n-0S6_WzA2Mj",
    code_challenge: "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
    code_challenge_method: "S256",
    prompt: "login",
    max_age: "0",
    ...changes,
  };
  for (const [key, value] of Object.entries(params)) {
    if (value !== null) url.searchParams.set(key, value);
  }
  return url.href;
}

interface Sent {
  url: string;
  init: RequestInit | undefined;
}

function recording(...answers: Array<[number, unknown]>): {
  sent: Sent[];
  fetch: (url: string, init?: RequestInit) => Promise<Response>;
} {
  const sent: Sent[] = [];
  return {
    sent,
    fetch: async (url, init) => {
      sent.push({ url, init });
      const [status, body] = answers.shift() ?? [500, null];
      return new Response(JSON.stringify(body), { status });
    },
  };
}

function form(values: Record<string, string>): FormData {
  const data = new FormData();
  for (const [key, value] of Object.entries(values)) data.set(key, value);
  return data;
}

async function begin(
  answer: [number, unknown],
  overrides: Partial<Parameters<typeof beginStepUp>[0]> = {},
): Promise<{ result: Awaited<ReturnType<typeof beginStepUp>>; sent: Sent[] }> {
  const api = recording(answer);
  const result = await beginStepUp({
    config: API,
    origin: ORIGIN,
    authorization: BEARER,
    fetchSite: "same-origin",
    form: form({ action_id: ACTION, from: "voice" }),
    fetch: api.fetch,
    ...overrides,
  });
  return { result, sent: api.sent };
}

describe("start — open a ceremony and go to Keycloak", () => {
  it("asks the API for one action's ceremony and follows its authorization URL", async () => {
    const { result, sent } = await begin([200, { authorize_url: authorizeUrl() }]);
    expect(result).toEqual({ kind: "redirect", location: authorizeUrl(), page: "voice" });
    expect(sent).toHaveLength(1);
    expect(sent[0]!.url).toBe("http://api:8000/admin/step-up");
    expect(sent[0]!.init?.method).toBe("POST");
    expect(JSON.parse(String(sent[0]!.init?.body))).toEqual({ action_id: ACTION });
    expect(new Headers(sent[0]!.init?.headers).get("authorization")).toBe(BEARER);
  });

  it.each([
    ["a cross-site post", { fetchSite: "cross-site" }, "cross_site_refused"],
    ["no Sec-Fetch-Site at all", { fetchSite: null }, "cross_site_refused"],
    ["no API base", { config: null }, "api_base_unconfigured"],
    ["no step-up origin", { origin: null }, "step_up_unconfigured"],
    ["no bearer", { authorization: null }, "no_credentials"],
    [
      "an action id that is not one",
      { form: form({ action_id: "x' or 1=1", from: "voice" }) },
      "action_unknown",
    ],
  ] as const)("refuses %s without dialling the API", async (_, overrides, code) => {
    const { result, sent } = await begin([200, { authorize_url: authorizeUrl() }], overrides);
    expect(result).toMatchObject({ kind: "result", code });
    expect(sent).toHaveLength(0);
  });

  it("brings the API's refusal back to the page the form was on", async () => {
    const { result } = await begin([409, { detail: { error: "four_eyes_self_approval" } }]);
    expect(result).toEqual({ kind: "result", code: "four_eyes_self_approval", page: "voice" });
  });

  it("does not follow an authorization URL that is not Keycloak's step-up endpoint", async () => {
    for (const bad of [
      authorizeUrl({}, "https://evil.example.test"),
      authorizeUrl({ prompt: null }),
      authorizeUrl({ prompt: "none" }),
      authorizeUrl({ max_age: "3600" }),
      authorizeUrl({ client_id: "admin-web" }),
      authorizeUrl({ code_challenge_method: "plain" }),
      authorizeUrl({ response_type: "token" }),
      authorizeUrl({ state: "short" }),
      `${ORIGIN}/realms/intake/protocol/openid-connect/logout`,
      "javascript:alert(1)",
    ]) {
      const { result } = await begin([200, { authorize_url: bad }]);
      expect(result).toMatchObject({ kind: "result", code: "api_refused" });
    }
  });

  it("a page outside the closed set returns to /step-up", async () => {
    const { result } = await begin([404, { error: "not_found" }], {
      form: form({ action_id: ACTION, from: "https://evil.example.test" }),
    });
    expect(result).toEqual({ kind: "result", code: "not_found", page: "step-up" });
  });
});

async function complete(
  query: string,
  ...answers: Array<[number, unknown]>
): Promise<{ result: Awaited<ReturnType<typeof completeStepUp>>; sent: Sent[] }> {
  const api = recording(...answers);
  const result = await completeStepUp({
    config: API,
    authorization: BEARER,
    query: new URLSearchParams(query),
    fallback: "cicd",
    fetch: api.fetch,
  });
  return { result, sent: api.sent };
}

const HONEST = `state=${STATE}&code=0b1c2d3e.4f5a-6b7c.8d9e`;

describe("callback — complete the ceremony and present the grant", () => {
  it("completes, then presents the grant on the action's own approve route", async () => {
    const { result, sent } = await complete(
      HONEST,
      [200, { grant: GRANT, action_id: ACTION, action: "admin.voice.canary.set" }],
      [200, { pending: {}, control: {} }],
    );
    expect(result).toEqual({ code: "approved", page: "voice" });
    expect(sent.map((s) => s.url)).toEqual([
      "http://api:8000/admin/step-up/complete",
      `http://api:8000/admin/voice/canary/pending/${ACTION}/approve`,
    ]);
    expect(JSON.parse(String(sent[0]!.init?.body))).toEqual({
      state: STATE,
      code: "0b1c2d3e.4f5a-6b7c.8d9e",
    });
    // the grant is the whole approve body: no assertion id, nothing else
    expect(JSON.parse(String(sent[1]!.init?.body))).toEqual({ step_up_grant: GRANT });
  });

  it("every console action maps to its own route and page", () => {
    expect(APPROVALS["admin.cicd.freeze.lift"]!.path(ACTION)).toBe(
      `/admin/cicd/freeze/lift/${ACTION}/approve`,
    );
    expect(APPROVALS["admin.access.review.sign"]!.path(ACTION)).toBe(
      `/admin/access/review/sign/${ACTION}/countersign`,
    );
    expect(approvalFor("admin.break_glass.open")?.page).toBe("step-up");
    expect(approvalFor("admin.voice.kill_switch.engage")).toBeNull();
    expect(approvalFor("__proto__")).toBeNull();
    expect(approvalFor("constructor")).toBeNull();
  });

  it("a cancelled login comes back as cancelled, without a dial", async () => {
    const { result, sent } = await complete(`error=access_denied&state=${STATE}`);
    expect(result).toEqual({ code: "step_up_cancelled", page: "cicd" });
    expect(sent).toHaveLength(0);
  });

  it.each([
    ["no state", "code=abc"],
    ["no code", `state=${STATE}`],
    ["a state that is not one", "state=%3Cscript%3E&code=abc"],
    ["a code with a space", `state=${STATE}&code=a%20b`],
  ])("%s is refused without a dial", async (_, query) => {
    const { result, sent } = await complete(query);
    expect(result).toEqual({ code: "step_up_unknown", page: "cicd" });
    expect(sent).toHaveLength(0);
  });

  it("the API's refusal of the ceremony is shown, and nothing is approved", async () => {
    const { result, sent } = await complete(HONEST, [
      403,
      { detail: { error: "step_up_without_webauthn" } },
    ]);
    expect(result).toEqual({ code: "step_up_without_webauthn", page: "cicd" });
    expect(sent).toHaveLength(1);
  });

  it.each([
    [
      "an action no approve route belongs to",
      { grant: GRANT, action_id: ACTION, action: "admin.voice.kill_switch.engage" },
    ],
    [
      "a grant that is not one",
      { grant: "assert-fresh-1", action_id: ACTION, action: "admin.cicd.freeze.lift" },
    ],
    [
      "an action id that is not one",
      { grant: GRANT, action_id: "../../admin", action: "admin.cicd.freeze.lift" },
    ],
  ])("%s is refused before anything is approved", async (_, body) => {
    const { result, sent } = await complete(HONEST, [200, body]);
    expect(result.code).toBe("action_unknown");
    expect(sent).toHaveLength(1);
  });

  it("the approve route's refusal lands on the action's page", async () => {
    const { result } = await complete(
      HONEST,
      [200, { grant: GRANT, action_id: ACTION, action: "admin.model_lanes.route.switch" }],
      [409, { detail: { error: "four_eyes_shared_credential" } }],
    );
    expect(result).toEqual({ code: "four_eyes_shared_credential", page: "model-lanes" });
  });

  it("a code the console does not know becomes api_refused, never text", () => {
    expect(apiResult({ detail: { error: "model_not_qualified" } })).toBe("api_refused");
    expect(apiResult({ error: "<b>no</b>" })).toBe("api_refused");
    expect(stepUpResultFrom("approved")).toBe("approved");
    expect(stepUpResultFrom("an arbitrary sentence")).toBeNull();
    expect(stepUpResultFrom(["approved", "approved"])).toBeNull();
  });
});

describe("configuration — the origin, the CSP and the return cookie", () => {
  it("takes Keycloak's origin from the environment, https only", () => {
    expect(stepUpOriginFromEnv({ INTAKE_ADMIN_STEP_UP_ORIGIN: ORIGIN })).toBe(ORIGIN);
    expect(stepUpOriginFromEnv({ INTAKE_ADMIN_STEP_UP_ORIGIN: "http://localhost:8080" })).toBe(
      "http://localhost:8080",
    );
    for (const bad of [
      undefined,
      "",
      "http://auth.staging.example.test",
      `${ORIGIN}/realms/intake`,
      `${ORIGIN}?x=1`,
      "https://user:pw@auth.staging.example.test",
      "not a url",
    ]) {
      expect(stepUpOriginFromEnv({ INTAKE_ADMIN_STEP_UP_ORIGIN: bad })).toBeNull();
    }
  });

  it("form-action admits that one origin beside 'self', and stays 'self' without it", () => {
    expect(buildCsp("bm9uY2U=", "production", ORIGIN)).toContain(`form-action 'self' ${ORIGIN}`);
    expect(buildCsp("bm9uY2U=", "production")).toMatch(/form-action 'self'$/);
    expect(buildCsp("bm9uY2U=", "production", ORIGIN)).not.toMatch(/unsafe-/);
    expect(() => buildCsp("bm9uY2U=", "production", "https://a.test; script-src *")).toThrow();
    expect(() => buildCsp("bm9uY2U=", "production", "*")).toThrow();
  });

  it("checks an authorization URL against the origin it was configured with", () => {
    expect(checkedAuthorizeUrl(authorizeUrl(), ORIGIN)).toBe(authorizeUrl());
    expect(checkedAuthorizeUrl(authorizeUrl(), "https://other.example.test")).toBeNull();
    expect(checkedAuthorizeUrl(42, ORIGIN)).toBeNull();
  });

  it("the return cookie carries a page and a language, and nothing else survives it", () => {
    const set = returnCookie("cicd", "en", true);
    expect(set).toBe(
      `${RETURN_COOKIE}=cicd.en; Path=/step-up; Max-Age=300; HttpOnly; SameSite=Lax; Secure`,
    );
    expect(returnFrom(`a=b; ${RETURN_COOKIE}=cicd.en`)).toEqual({ page: "cicd", lang: "en" });
    expect(returnFrom(`${RETURN_COOKIE}=https://evil.test.en`)).toEqual({
      page: "step-up",
      lang: "tr",
    });
    expect(returnFrom(null)).toEqual({ page: "step-up", lang: "tr" });
    expect(
      destination("https://admin.x.test/step-up/callback", "voice", "en", "approved").href,
    ).toBe("https://admin.x.test/voice?step_up=approved&lang=en");
  });
});

describe("the /step-up page and the copy", () => {
  it("shows one id-shaped action with its Onayla, and nothing for anything else", () => {
    const markup = renderToStaticMarkup(
      createElement(StepUpPage, { actionId: ACTION, result: null, lang: "tr" }),
    );
    expect(markup).toContain(`name="action_id" value="${ACTION}"`);
    expect(markup).toContain('name="from" value="step-up"');
    expect(markup).toContain(">Onayla</button>");
    const injected = renderToStaticMarkup(
      createElement(StepUpPage, { actionId: '"><script>', result: null, lang: "tr" }),
    );
    expect(injected).not.toContain("<form");
    expect(injected).toContain("data-step-up-empty");
  });

  it("every outcome has a sentence in both languages", () => {
    for (const code of STEP_UP_RESULTS) {
      expect(COPY.tr.results[code].length).toBeGreaterThan(0);
      expect(COPY.en.results[code].length).toBeGreaterThan(0);
    }
  });

  it(
    "is accessible in both languages",
    async () => {
      for (const lang of ["tr", "en"] as const) {
        const tree = createElement(StepUpPage, { actionId: ACTION, result: "approved", lang });
        expect(await violations(documentFor(tree, lang))).toEqual([]);
      }
    },
    AXE_TIMEOUT_MS,
  );
});
