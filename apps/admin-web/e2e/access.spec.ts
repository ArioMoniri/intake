/**
 * INT-366 — the rendered access review (files/08 §2.7, §3 Access & identity).
 *
 * **What this runs against.** Every body is a recording, made in tests only by
 * `scripts/dev/record_access_fixture.py` from the shipped code: the Keycloak
 * admin adapter over the recorded realm (`tests/admin/fixtures/
 * keycloak_admin_realm.json`), the review generator and the route's own view.
 * `tests/admin/test_access_review.py` holds the committed files equal to it.
 * - `access.payload.json` — both console sections countersigned 40 days before
 *   the recording, tenant-a's clinician section 120 days before (overdue), and
 *   one offboarding with its three manual steps open;
 * - `access.lapsed.payload.json` — the same realm with no console review.
 * The two 503 bodies are the API's own error shape (`{"error": code}`).
 *
 * The spec drives the page's own server-side loader through an injected
 * `fetch` and renders the page's own React tree to static markup.
 *
 * **The properties, each with a near-miss.** Admission is the API's gate; a
 * lapsed review shows `platform_owner` and `tenant_admin` read-only and a
 * current one shows none; a body whose read-only roles do not follow from its
 * age, a holder row carrying a name or mail field, or a 64-hex value is
 * refused, not painted; the page is read-only.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { AccessConsole } from "../src/access/console";
import { loadAccessReview, type AccessState } from "../src/access/load";
import {
  AccessChainMaterialLeaked,
  AccessDirectoryLeaked,
  AccessReviewInconsistent,
  renderAccessReview,
  type AccessReviewPayload,
} from "../src/access/module";
import { opsConfigFromEnv } from "../src/ops/access";
import type { FetchLike } from "../src/ops/load";

const FIXTURES = join(__dirname, "fixtures");
const API = "https://api.intake.test";
const BEARER = "Bearer kc-admin-session";

function read(name: string): AccessReviewPayload {
  return JSON.parse(readFileSync(join(FIXTURES, name), "utf8")) as AccessReviewPayload;
}

const current = (): AccessReviewPayload => read("access.payload.json");
const lapsed = (): AccessReviewPayload => read("access.lapsed.payload.json");

function answering(status: number, body: unknown): { fetch: FetchLike; urls: string[] } {
  const urls: string[] = [];
  const fetch: FetchLike = async (url) => {
    urls.push(url);
    return new Response(JSON.stringify(body), {
      status,
      headers: { "content-type": "application/json" },
    });
  };
  return { fetch, urls };
}

async function load(status: number, body: unknown, authorization: string | null = BEARER) {
  const recorded = answering(status, body);
  const state = await loadAccessReview({
    config: opsConfigFromEnv({ INTAKE_ADMIN_API_BASE: API }),
    authorization,
    fetch: recorded.fetch,
    dayUnit: "gün",
  });
  return { state, urls: recorded.urls };
}

function html(state: AccessState, lang: "tr" | "en" = "tr"): string {
  return renderToStaticMarkup(createElement(AccessConsole, { state, lang }));
}

describe("admission is the API's", () => {
  it("dials nothing without a bearer", async () => {
    const { state, urls } = await load(200, current(), null);
    expect(state).toEqual({ kind: "not_admitted", reason: "no_credentials" });
    expect(urls).toEqual([]);
  });

  it("asks exactly the review route with the caller's bearer", async () => {
    const { state, urls } = await load(200, current());
    expect(state.kind).toBe("console");
    expect(urls).toEqual([`${API}/admin/access/review`]);
  });

  it("renders a role refusal as a refusal", async () => {
    const { state } = await load(403, { error: "forbidden" });
    expect(state).toEqual({ kind: "not_admitted", reason: "role_not_permitted" });
    expect(html(state)).toContain('data-refusal="role_not_permitted"');
  });

  it.each([["access_review_unconfigured"], ["directory_unavailable"]])(
    "names the identity 503 %s instead of calling the API unreachable",
    async (code) => {
      const { state } = await load(503, { error: code });
      expect(state).toEqual({ kind: "identity_unavailable", reason: code });
      expect(html(state)).toContain(`data-unavailable="${code}"`);
    },
  );

  it("near miss: any other 503 is the API being unreachable", async () => {
    const { state } = await load(503, { error: "something_else" });
    expect(state).toEqual({ kind: "unavailable", reason: "api_unreachable" });
  });
});

describe("the review", () => {
  it("shows a current review with nothing read-only", async () => {
    const { state } = await load(200, current());
    const page = html(state);
    expect(page).toContain('data-read-only=""');
    expect(page).toContain('data-review-age="40.0 gün"');
    expect(page).toContain('data-section="clinicians:tenant-a" data-overdue="true"');
    expect(page).toContain('data-section="platform_owner" data-overdue="false"');
  });

  it("shows a lapsed review making platform_owner and tenant_admin read-only", async () => {
    const { state } = await load(200, lapsed());
    const page = html(state, "en");
    expect(page).toContain('data-read-only="platform_owner,tenant_admin"');
    expect(page).toContain("Never countersigned");
  });

  it("marks the accounts past sixty days without a login", async () => {
    const { state } = await load(200, current());
    const page = html(state);
    expect(page).toContain('data-subject="kc-sub-clinician-dormant" data-dormant="true"');
    expect(page).toContain('data-subject="kc-sub-clinician-fifty-nine" data-dormant="false"');
  });

  it("lists the open offboarding with its manual steps", async () => {
    const { state } = await load(200, current());
    expect(html(state)).toContain("grafana, langfuse, unleash");
  });

  it("offers no control: signing and offboarding are the API's ceremonies", async () => {
    const { state } = await load(200, current());
    const page = html(state);
    expect(page).not.toContain("<form");
    expect(page).not.toContain("<button");
    expect(page).not.toContain("style=");
  });
});

describe("refusals", () => {
  it("near miss: read-only roles that do not follow from the age are refused", () => {
    const body = lapsed();
    body.status.read_only_roles = [];
    expect(() => renderAccessReview(body, "gün")).toThrow(AccessReviewInconsistent);
  });

  it("near miss: a current review claiming read-only roles is refused", () => {
    const body = current();
    body.status.read_only_roles = ["platform_owner", "tenant_admin"];
    expect(() => renderAccessReview(body, "gün")).toThrow(AccessReviewInconsistent);
  });

  it("near miss: a section whose overdue flag disagrees with its age is refused", () => {
    const body = current();
    body.sections[2]!.overdue = false;
    expect(() => renderAccessReview(body, "gün")).toThrow(AccessReviewInconsistent);
  });

  it("refuses a holder row carrying a directory field", () => {
    const body = current();
    (body.holders[0] as unknown as Record<string, unknown>)["email"] = "x@example.invalid";
    expect(() => renderAccessReview(body, "gün")).toThrow(AccessDirectoryLeaked);
  });

  it("refuses a username that is prose", () => {
    const body = current();
    body.holders[0]!.username = "Synthetic Owner";
    expect(() => renderAccessReview(body, "gün")).toThrow(AccessDirectoryLeaked);
  });

  it("refuses a 64-hex value anywhere", () => {
    const body = current();
    body.sections[0]!.review_digest = "a".repeat(64);
    expect(() => renderAccessReview(body, "gün")).toThrow(AccessChainMaterialLeaked);
  });

  it("turns a refused body into payload_refused, never a half-painted page", async () => {
    const body = current();
    body.status.read_only_roles = ["platform_owner"];
    const { state } = await load(200, body);
    expect(state).toEqual({ kind: "unavailable", reason: "payload_refused" });
  });
});
