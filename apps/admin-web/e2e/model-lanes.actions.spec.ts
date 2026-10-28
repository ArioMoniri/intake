/**
 * INT-428 — the Model lanes module, write side: the forms the page offers and
 * the handler behind them (files/08 §3, §8.2; ADR-035).
 *
 * **The properties, each with a near-miss.** Two tier-1 buttons are always
 * there — "Disable hosted lanes" and "Switch to GPU / self-hosted" — and are
 * one key; a route switch, a hosted release and a provider key are requests
 * for a second key; there is no approve form and no `mock` option anywhere;
 * nothing reaches the API that the API would refuse; a refusal comes back as
 * its code, and only a code. **The provider key** is a password field the
 * page never fills, goes to the API in one request body, and appears in no
 * outcome, no cookie and no rendered byte — only the API's last four do.
 */
import { describe, expect, it } from "vitest";

import {
  planModelLanesAction,
  stagedCookie,
  submitModelLanesAction,
  type Outcome,
} from "../src/model-lanes/actions";
import { resultFrom, stagedFrom } from "../src/model-lanes/load";
import { opsConfigFromEnv } from "../src/ops/access";
import {
  API,
  TYPED_KEY,
  html,
  load,
  page,
  payload,
  realPhi,
  recordedFetch,
  withHostedDisabled,
  withPending,
  type Call,
  type Recorded,
} from "./model-lanes.fixture";

function forms(markup: string): string[] {
  return [...markup.matchAll(/<form [^>]*data-control="([a-z_]+)"/g)].map((m) => m[1]!);
}

// ------------------------------------------------------------------ the forms

describe("the forms — one key toward the GPU, a request for two toward a provider", () => {
  it("always offers the two tier-1 buttons, posting to the page's own handler", async () => {
    const markup = await page(payload());
    expect(markup).toMatch(/data-control="hosted_disable" data-tier="1"/);
    expect(markup).toMatch(/data-control="self_hosted_engage" data-tier="1"/);
    expect(markup).toContain('<button type="submit">Disable hosted lanes</button>');
    expect(markup).toContain('<button type="submit">Switch to GPU / self-hosted</button>');
    const posts = markup.match(/action="\/model-lanes\/action" method="post"/g)?.length;
    expect(posts).toEqual(forms(markup).length);
  });

  it("a switch per lane and role, a key form per provider, a release only while disabled", async () => {
    expect(forms(await page(payload()))).toEqual([
      "hosted_disable",
      "self_hosted_engage",
      "route_switch",
      "route_switch",
      "route_switch",
      "route_switch",
      "key_set",
    ]);
    expect(forms(await page(withHostedDisabled()))).toContain("hosted_release");
    expect(forms(await page(realPhi()))).not.toContain("key_set");
  });

  it("offers attested self-hosted models and the hosted snapshots — never an unattested row", async () => {
    const markup = await page(payload());
    const llm = /data-target="llm"[\s\S]*?<\/form>/.exec(markup)![0];
    expect(llm).toContain('value="Qwen/Qwen3.6-35B-A3B@995ad96eacd98c81ed38be0c5b274b04031597b0"');
    expect(llm).toContain('<option value="gpt-4o-mini" selected="">');
    expect(llm).toContain('<option value="hosted:openai" selected="">');
    expect(llm).not.toContain("qwen3.5-9b");
  });

  it("offers no hosted route, model or fallback where hosted lanes are not part of the deployment", async () => {
    const markup = await page(realPhi());
    expect(markup).not.toContain('value="hosted:openai"');
    expect(markup).not.toContain('name="fallback"');
    expect(markup).not.toContain("gpt-4o-mini");
  });

  it("has no mock option anywhere", async () => {
    for (const doc of [payload(), realPhi(), withHostedDisabled()]) {
      expect(await page(doc)).not.toMatch(/mock/i);
    }
  });

  it("lists pending ceremonies; a pending one carries the step-up's Approve", async () => {
    const markup = await page(withPending());
    expect(markup).toContain('data-ceremony="route_switch"');
    // INT-563: the form posts the action id and its page, nothing else
    expect(markup).toMatch(
      /<form class="inline-form" data-step-up="[^"]+" action="\/step-up\/start" method="post"><input type="hidden" name="action_id" value="[^"]+"\/><input type="hidden" name="from" value="model-lanes"\/><input type="hidden" name="lang" value="en"\/><button type="submit">Approve<\/button><\/form>/,
    );
    expect(markup).not.toContain("step_up_unwired");
    expect(markup).not.toMatch(/name="(assertion_id|step_up_grant)"/);
  });

  it("the key field is a password input that is never given a value", async () => {
    const markup = await page(payload());
    const input = /<input type="password"[^>]*name="api_key"[^>]*>/.exec(markup)?.[0];
    expect(input).toBeDefined();
    expect(input).not.toMatch(/value=/);
    expect(input).toContain('autoComplete="off"');
  });
});

// ------------------------------------------------------------------ the handler

function form(fields: Record<string, string | string[]>): FormData {
  const data = new FormData();
  for (const [key, value] of Object.entries(fields)) {
    for (const one of Array.isArray(value) ? value : [value]) data.append(key, one);
  }
  return data;
}

const REASON = {
  reason_class: "incident_mitigation",
  justification: "GPU lanes recovered; take hosted lanes out of the path.",
};

async function submit(
  fields: Record<string, string | string[]>,
  opts: { site?: string | null; answer?: Recorded } = {},
): Promise<Outcome & { calls: Call[] }> {
  const answer = opts.answer ?? { status: 200, body: { changed: true } };
  const paths = [
    "/admin/model-lanes/hosted/disable",
    "/admin/model-lanes/self-hosted",
    "/admin/model-lanes/hosted/release",
    "/admin/model-lanes/route/llm",
    "/admin/model-lanes/route/llm.council.chair",
    "/admin/model-lanes/keys/openai",
  ];
  const { fetch, calls } = recordedFetch(Object.fromEntries(paths.map((p) => [p, answer])));
  const outcome = await submitModelLanesAction({
    config: opsConfigFromEnv({ INTAKE_ADMIN_API_BASE: API }),
    authorization: "Bearer kc:platform_owner",
    fetchSite: opts.site === undefined ? "same-origin" : opts.site,
    form: form(fields),
    fetch,
  });
  return { ...outcome, calls };
}

describe("the handler — nothing reaches the API that the API would refuse", () => {
  it("disables hosted lanes with one POST, the bearer and the closed body", async () => {
    const { code, calls } = await submit({ action: "hosted_disable", ...REASON });
    expect(code).toEqual("applied");
    expect(calls).toEqual([
      {
        url: `${API}/admin/model-lanes/hosted/disable`,
        method: "POST",
        authorization: "Bearer kc:platform_owner",
        body: REASON,
      },
    ]);
    const again = await submit(
      { action: "hosted_disable", ...REASON },
      { answer: { status: 200, body: { changed: false } } },
    );
    expect(again.code).toEqual("unchanged");
  });

  it("switches the chosen lanes to the GPU, and shows the API's refusal plainly", async () => {
    const { code, calls } = await submit({
      action: "self_hosted_engage",
      lanes: ["llm", "asr", "llm"],
      ...REASON,
    });
    expect(code).toEqual("applied");
    expect(calls[0]).toMatchObject({
      method: "POST",
      url: `${API}/admin/model-lanes/self-hosted`,
      body: { ...REASON, lanes: ["llm", "asr"] },
    });
    const refused = await submit(
      { action: "self_hosted_engage", lanes: ["tts"], ...REASON },
      {
        answer: { status: 409, body: { detail: { error: "model_lanes_self_hosted_not_healthy" } } },
      },
    );
    expect(refused.code).toEqual("model_lanes_self_hosted_not_healthy");
    const { state } = await load(payload());
    expect(html(state, "en", refused.code)).toContain(
      'data-result="model_lanes_self_hosted_not_healthy"',
    );
  });

  it("requests a route switch for a lane or a dotted role, with the closed body", async () => {
    const { code, calls } = await submit(
      {
        action: "route_switch",
        role: "llm.council.chair",
        route: "hosted:openai",
        model: "gpt-4o-mini",
        fallback: "",
        fallback_model: "",
        ...REASON,
      },
      { answer: { status: 200, body: { action_id: "pa-0003", state: "pending" } } },
    );
    expect(code).toEqual("requested");
    expect(calls).toEqual([
      {
        url: `${API}/admin/model-lanes/route/llm.council.chair`,
        method: "PUT",
        authorization: "Bearer kc:platform_owner",
        body: {
          ...REASON,
          route: "hosted:openai",
          model: "gpt-4o-mini",
          fallback: null,
          fallback_model: null,
        },
      },
    ]);
  });

  it("requests a hosted release as a request only", async () => {
    const { code, calls } = await submit({ action: "hosted_release", ...REASON });
    expect(code).toEqual("requested");
    expect(calls[0]).toMatchObject({ url: `${API}/admin/model-lanes/hosted/release` });
  });

  it.each([
    [{ action: "approve" }, "action_unknown"],
    [{ action: "route_switch", role: "llm", route: "mock" }, "model_lanes_route_unknown"],
    [{ action: "route_switch", role: "llm; drop", route: "self_hosted" }, "model_role_unknown"],
    [
      { action: "route_switch", role: "llm", route: "self_hosted", fallback: "x" },
      "model_lanes_provider_unknown",
    ],
    [
      { action: "route_switch", role: "llm", route: "self_hosted", model: "a b" },
      "model_key_malformed",
    ],
    [{ action: "self_hosted_engage" }, "model_lanes_lane_unknown"],
    [{ action: "self_hosted_engage", lanes: "mock" }, "model_lanes_lane_unknown"],
    [{ action: "key_set", provider: "anthropic" }, "model_lanes_provider_unknown"],
    [{ action: "hosted_disable", reason_class: "because" }, "model_lanes_reason_class_unknown"],
  ])("refuses %j as %s without dialling", async (fields, expected) => {
    const { code, calls } = await submit({ ...REASON, ...fields });
    expect(code).toEqual(expected);
    expect(calls).toEqual([]);
  });

  it("refuses a cross-site post before anything is dialled (near miss: same-origin)", async () => {
    for (const site of ["cross-site", "same-site", "none", null]) {
      const { code, calls } = await submit({ action: "hosted_disable", ...REASON }, { site });
      expect(code).toEqual("cross_site_refused");
      expect(calls).toEqual([]);
    }
  });

  it("carries the API's refusal code back, and only a code", async () => {
    const coded = await submit(
      { action: "hosted_release", ...REASON },
      { answer: { status: 409, body: { detail: { error: "model_lanes_nothing_to_change" } } } },
    );
    expect(coded.code).toEqual("model_lanes_nothing_to_change");
    const prose = await submit(
      { action: "hosted_release", ...REASON },
      { answer: { status: 409, body: { detail: { error: "Ayşe could not release it" } } } },
    );
    expect(prose.code).toEqual("api_refused");
    const expired = await submit(
      { action: "hosted_release", ...REASON },
      { answer: { status: 401, body: {} } },
    );
    expect(expired.code).toEqual("token_refused");
  });

  it("shows a result code it knows and nothing it does not", () => {
    expect(resultFrom("staged")).toEqual("staged");
    expect(resultFrom("<script>")).toBeNull();
    expect(resultFrom(["applied", "requested"])).toBeNull();
  });
});

// ------------------------------------------------------------------ the key

describe("the provider key goes to the API once and is never echoed", () => {
  const keyForm = { action: "key_set", provider: "openai", api_key: TYPED_KEY, ...REASON };
  const stagedAnswer = { action_id: "pa-0004", key: { state: "staged", last4: "4f7e" } };

  it("sends it in exactly one PUT body, and the outcome carries only the API's last four", async () => {
    const outcome = await submit(keyForm, { answer: { status: 200, body: stagedAnswer } });
    expect(outcome.calls).toHaveLength(1);
    expect(outcome.calls[0]).toMatchObject({
      method: "PUT",
      url: `${API}/admin/model-lanes/keys/openai`,
      body: { ...REASON, api_key: TYPED_KEY },
    });
    const { calls, ...rest } = outcome;
    expect(calls).toHaveLength(1);
    expect(rest).toEqual({ code: "staged", staged: { provider: "openai", last4: "4f7e" } });
    expect(JSON.stringify(rest)).not.toContain(TYPED_KEY);
  });

  it("never renders the key: after a submit the page shows only staged · …last4", async () => {
    const outcome = await submit(keyForm, { answer: { status: 200, body: stagedAnswer } });
    const cookie = stagedCookie(outcome.staged!);
    expect(cookie).not.toContain(TYPED_KEY);
    expect(cookie).toMatch(/HttpOnly; SameSite=Strict; Secure$/);
    const staged = stagedFrom(cookie.split(";")[0]!.split("=")[1]);
    const { state } = await load(payload());
    const markup = html(state, "en", outcome.code, staged);
    expect(markup).toContain("openai · staged · …<code>4f7e</code>");
    expect(markup).not.toContain(TYPED_KEY);
    expect(markup).not.toContain(TYPED_KEY.slice(0, 12));
    expect(/<input type="password"[^>]*name="api_key"[^>]*>/.exec(markup)![0]).not.toMatch(
      /value=/,
    );
  });

  it("drops an answer that echoes more than four characters, and a malformed key is never sent", async () => {
    const echoed = await submit(keyForm, {
      answer: { status: 200, body: { key: { state: "staged", last4: TYPED_KEY } } },
    });
    expect(echoed.code).toEqual("staged");
    expect(echoed.staged).toBeUndefined();
    const refused = await submit(keyForm, {
      answer: { status: 422, body: { detail: { error: TYPED_KEY } } },
    });
    expect(refused.code).toEqual("api_refused");
    const short = await submit({ ...keyForm, api_key: TYPED_KEY.slice(0, 12) });
    expect(short.code).toEqual("model_lanes_key_malformed");
    expect(short.calls).toEqual([]);
    expect(JSON.stringify(short)).not.toContain(TYPED_KEY.slice(0, 12));
  });

  it("reads back only a provider and four key characters from the cookie", () => {
    expect(stagedFrom("openai.4f7e")).toEqual({ provider: "openai", last4: "4f7e" });
    expect(stagedFrom(`openai.${TYPED_KEY}`)).toBeNull();
    expect(stagedFrom("anthropic.4f7e")).toBeNull();
    expect(stagedFrom(undefined)).toBeNull();
  });

  it("plans the key body without trimming or reshaping it", () => {
    const plan = planModelLanesAction(form(keyForm));
    expect(plan).toMatchObject({ ok: true, method: "PUT", path: "/admin/model-lanes/keys/openai" });
    const padded = planModelLanesAction(form({ ...keyForm, api_key: ` ${TYPED_KEY}` }));
    expect(padded).toEqual({ ok: false, code: "model_lanes_key_malformed" });
  });
});
