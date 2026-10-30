/**
 * INT-562 — the rendered Safety queue (files/08 §3 "Safety queue", §0c F19;
 * invariant 49), over `GET /admin/safety-queue` (INT-406).
 *
 * **What this runs against.** `safety-queue.payload.json` is a recording made
 * by `scripts/dev/record_safety_queue_fixture.py` from the shipped code: the
 * inbox's own entry constructors, its own ordering and the route's own row
 * projection, over synthetic ids (invariant 6). `tests/admin/
 * test_safety_queue.py` holds the committed file equal to it. The spec drives
 * the page's own server-side loader through an injected `fetch` and renders
 * the page's own React tree to static markup.
 *
 * **The properties, each with a near miss.**
 * - Admission is the API's gate; a 503 from the inbox is this page's own
 *   unavailable state, named, with its next step — never an empty queue, which
 *   would read as "nobody is waiting".
 * - The order is the inbox's (INT-406, INT-553's F3 on the API): open entries
 *   first, oldest first; then the answered ones, newest answer first. A body
 *   out of that order is refused, not re-sorted: the page decides nothing the
 *   server did not.
 * - Ids and clocks only (invariant 6): an entry id outside `sx_` + 32 hex, a
 *   rule id, subject or session id that is not id-shaped, is refused.
 * - The vocabularies are sealed: a kind, a register or an age band outside
 *   the inbox's enums is refused.
 * - Every open entry offers one acknowledgement, a plain form to this app's
 *   own handler; an answered entry shows who and when, and no form. The
 *   handler refuses a cross-site post and a malformed entry id before dialling,
 *   forwards nothing but the id, and answers a code, never the API's prose.
 * - The empty queue says what fills it; the unavailable inbox says what fills
 *   it; a refused caller keeps the shell.
 * - Every state passes axe, and no `style` attribute is rendered (the CSP).
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { JSDOM } from "jsdom";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { opsConfigFromEnv } from "../src/ops/access";
import type { FetchLike } from "../src/ops/load";
import { CONSOLE_PAGES } from "../src/ops/nav";
import {
  isResultCode,
  planAcknowledge,
  submitAcknowledge,
  type ResultCode,
} from "../src/safety-queue/actions";
import { SafetyQueueConsole } from "../src/safety-queue/console";
import { COPY } from "../src/safety-queue/copy";
import { loadSafetyQueue, type SafetyQueueState } from "../src/safety-queue/load";
import {
  AGE_BANDS,
  KINDS,
  REGISTERS,
  SafetyQueueLeaked,
  SafetyQueueOrderRefused,
  SafetyQueueVocabularyRefused,
  renderSafetyQueue,
  type QueueRowPayload,
  type SafetyQueuePayload,
} from "../src/safety-queue/module";
import { EMPTIES } from "../src/ui/fills";
import { AXE_TIMEOUT_MS, documentFor, violations } from "./support/axe";

const FIXTURES = join(__dirname, "fixtures");
const API = "https://api.intake.test";
const BEARER = "Bearer kc-admin-session";

function recorded(): SafetyQueuePayload {
  return JSON.parse(
    readFileSync(join(FIXTURES, "safety-queue.payload.json"), "utf8"),
  ) as SafetyQueuePayload;
}

function answering(
  status: number,
  body: unknown,
): { fetch: FetchLike; calls: RequestInit[]; urls: string[] } {
  const urls: string[] = [];
  const calls: RequestInit[] = [];
  const fetch: FetchLike = async (url, init) => {
    urls.push(url);
    calls.push(init ?? {});
    return new Response(JSON.stringify(body), {
      status,
      headers: { "content-type": "application/json" },
    });
  };
  return { fetch, calls, urls };
}

async function load(status: number, body: unknown, authorization: string | null = BEARER) {
  const api = answering(status, body);
  const state = await loadSafetyQueue({
    config: opsConfigFromEnv({ INTAKE_ADMIN_API_BASE: API }),
    authorization,
    fetch: api.fetch,
  });
  return { state, urls: api.urls };
}

function html(state: SafetyQueueState, lang: "tr" | "en" = "tr", result: ResultCode | null = null) {
  return renderToStaticMarkup(createElement(SafetyQueueConsole, { state, lang, result }));
}

function dom(state: SafetyQueueState, lang: "tr" | "en" = "tr"): Document {
  return new JSDOM(html(state, lang)).window.document;
}

const text = (el: Element | null): string => (el?.textContent ?? "").replace(/\s+/g, " ").trim();

function queued(payload: SafetyQueuePayload = recorded()): SafetyQueueState {
  return { kind: "console", view: renderSafetyQueue(payload) };
}

function form(fields: Record<string, string>): FormData {
  const data = new FormData();
  for (const [key, value] of Object.entries(fields)) data.set(key, value);
  return data;
}

// --- the recording ---------------------------------------------------------------------

describe("the recording is the inbox's queue", () => {
  const rows = recorded().entries;

  it("holds four open entries then one answered, every kind and register the inbox has", () => {
    expect(rows.map((r) => r.acknowledged)).toEqual([false, false, false, false, true]);
    expect(new Set(rows.map((r) => r.kind))).toEqual(
      new Set(["red", "red_on_site", "visit_rescheduled"]),
    );
    expect(rows.map((r) => r.register)).toEqual(["CALM", null, null, "ALERT", "SILENT"]);
    expect(rows.map((r) => r.age_band)).toEqual([
      "past_sla",
      "past_sla",
      "within_sla",
      "within_sla",
      null,
    ]);
  });

  it("carries ids and clocks only: no name, no mail, no words", () => {
    for (const row of rows) {
      for (const value of Object.values(row)) {
        if (typeof value === "string") expect(value).not.toMatch(/\s|@/);
      }
    }
  });
});

// --- admission and the inbox's own 503s ------------------------------------------------

describe("admission is the API's", () => {
  it("dials nothing without a bearer", async () => {
    const { state, urls } = await load(200, recorded(), null);
    expect(state).toEqual({ kind: "not_admitted", reason: "no_credentials" });
    expect(urls).toEqual([]);
  });

  it("asks exactly the queue route with the caller's bearer", async () => {
    const { state, urls } = await load(200, recorded());
    expect(state.kind).toBe("console");
    expect(urls).toEqual([`${API}/admin/safety-queue`]);
  });

  it("renders a role refusal as a refusal, with the shell", async () => {
    const { state } = await load(403, { error: "forbidden" });
    expect(state).toEqual({ kind: "not_admitted", reason: "role_not_permitted" });
    const doc = dom(state);
    expect(doc.querySelector(".refusal[data-refusal='role_not_permitted']")).not.toBeNull();
    expect(
      doc.querySelector("nav.console-nav [aria-current='page'][data-page-link='safety-queue']"),
    ).not.toBeNull();
  });

  it.each([
    ["safety_inbox_unconfigured"],
    ["safety_inbox_unreachable"],
    ["safety_inbox_contended"],
  ])(
    "names the inbox 503 %s instead of calling the API unreachable, and never an empty queue",
    async (code) => {
      const { state } = await load(503, { error: code });
      expect(state).toEqual({ kind: "inbox_unavailable", reason: code });
      const doc = dom(state);
      expect(doc.querySelector(`.refusal[data-unavailable='${code}']`)).not.toBeNull();
      expect(doc.querySelector(".next-step[data-next-step]")).not.toBeNull();
      expect(doc.querySelector("[data-empty]")).toBeNull();
      expect(doc.querySelector("table")).toBeNull();
    },
  );

  it("near miss: another 503 is the API unreachable", async () => {
    const { state } = await load(503, { error: "something_else" });
    expect(state).toEqual({ kind: "unavailable", reason: "api_unreachable" });
  });

  it("turns a refused body into payload_refused, never a half-painted page", async () => {
    const bent = recorded();
    bent.entries[0]!.acknowledged_by = "Dr Ayşe Yılmaz";
    const { state } = await load(200, bent);
    expect(state).toEqual({ kind: "unavailable", reason: "payload_refused" });
  });
});

// --- the order is the inbox's -----------------------------------------------------------

describe("the order is the inbox's, never the page's", () => {
  it("open first, oldest first; then answered, newest answer first", () => {
    const view = renderSafetyQueue(recorded());
    expect(view.rows.map((r) => r.acknowledged)).toEqual([false, false, false, false, true]);
    const open = view.rows.filter((r) => !r.acknowledged).map((r) => r.createdAt);
    expect(open).toEqual([...open].sort());
    expect(view.open).toBe(4);
    expect(view.pastSla).toBe(2);
  });

  it("near miss: an open entry after an answered one is refused", () => {
    const bent = recorded();
    bent.entries.push(bent.entries.shift()!);
    expect(() => renderSafetyQueue(bent)).toThrow(SafetyQueueOrderRefused);
  });

  it("near miss: open entries out of age order are refused", () => {
    const bent = recorded();
    [bent.entries[0], bent.entries[2]] = [bent.entries[2]!, bent.entries[0]!];
    expect(() => renderSafetyQueue(bent)).toThrow(SafetyQueueOrderRefused);
  });

  it("near miss: answered entries not newest-answer-first are refused", () => {
    const bent = recorded();
    const answered = bent.entries[4]!;
    const older: QueueRowPayload = {
      ...answered,
      entry_id: "sx_" + "a".repeat(32),
      acknowledged_at: "2026-10-28T06:00:00+00:00",
    };
    bent.entries.push(older);
    expect(() => renderSafetyQueue(bent)).not.toThrow();
    bent.entries.splice(4, 2, older, answered);
    expect(() => renderSafetyQueue(bent)).toThrow(SafetyQueueOrderRefused);
  });
});

// --- ids only, sealed vocabularies -------------------------------------------------------

describe("ids and clocks only; the vocabularies are sealed", () => {
  const bend = (patch: Partial<QueueRowPayload>): SafetyQueuePayload => {
    const payload = recorded();
    payload.entries[0] = { ...payload.entries[0]!, ...patch };
    return payload;
  };

  it.each([
    ["an entry id outside sx_ + 32 hex", { entry_id: "sx_short" }],
    ["a subject with a space", { acknowledged_by: "Dr Ayşe" }],
    ["a rule id with a space", { rule_ids: ["göğüs ağrısı"] }],
    ["a session id that is prose", { session_id: "the patient from this morning" }],
    ["a tenant id with a mail", { tenant_id: "a@b.c" }],
  ])("refuses %s", (_name, patch) => {
    expect(() => renderSafetyQueue(bend(patch as Partial<QueueRowPayload>))).toThrow(
      SafetyQueueLeaked,
    );
  });

  it.each([
    ["a kind", { kind: "clinic_note" }],
    ["a register", { register: "LOUD" }],
    ["an age band", { age_band: "late" }],
  ])("refuses %s outside the inbox's enum", (_name, patch) => {
    expect(() => renderSafetyQueue(bend(patch as Partial<QueueRowPayload>))).toThrow(
      SafetyQueueVocabularyRefused,
    );
  });

  it("the sealed vocabularies are the inbox's", () => {
    expect([...KINDS]).toEqual(["red", "red_on_site", "visit_rescheduled", "visit_cancelled"]);
    expect([...REGISTERS]).toEqual(["ALERT", "CALM", "SILENT", "DEFERRED_CLINICIAN"]);
    expect([...AGE_BANDS]).toEqual(["within_sla", "past_sla"]);
  });

  it("near miss: a register on a transition is refused (only a RED is told in one)", () => {
    expect(() => renderSafetyQueue(bend({ kind: "visit_rescheduled", register: "CALM" }))).toThrow(
      SafetyQueueVocabularyRefused,
    );
  });
});

// --- the page ---------------------------------------------------------------------------

describe("the page: every open entry offers one acknowledgement", () => {
  const doc = dom(queued());
  const c = COPY.tr;

  it("renders the rows in the inbox's order with their ids, kind, rules, register, clocks", () => {
    const rows = [...doc.querySelectorAll("tbody tr[data-entry]")];
    expect(rows.length).toBe(5);
    expect(rows.map((r) => r.getAttribute("data-kind"))).toEqual([
      "red",
      "red_on_site",
      "visit_rescheduled",
      "red",
      "red",
    ]);
    expect(rows.map((r) => r.getAttribute("data-age-band"))).toEqual([
      "past_sla",
      "past_sla",
      "within_sla",
      "within_sla",
      "",
    ]);
    const first = rows[0]!;
    expect(text(first.querySelector("[data-col='kind']"))).toBe(c.kinds.red);
    expect(text(first.querySelector("[data-col='register']"))).toBe(c.registers.CALM);
    expect(first.querySelector("[data-col='rules'] code")!.textContent).toBe(
      "rf.sentetik_yasamsal",
    );
    expect(first.querySelector("[data-col='created'] time")).not.toBeNull();
    expect(text(first.querySelector("[data-col='age']"))).toBe(
      `265 dk · SLA 240 dk · ${c.bands.past_sla}`,
    );
  });

  it("the page's summary counts open entries and those past their SLA, in words", () => {
    const summary = doc.querySelector(".status-summary");
    expect(text(summary)).toBe(`4 ${c.summary.open} · 2 ${c.summary.pastSla}`);
  });

  it("an open entry has one form posting only its id to this app's handler", () => {
    const forms = [...doc.querySelectorAll("tbody tr[data-entry] form")];
    expect(forms.length).toBe(4);
    for (const f of forms) {
      expect(f.getAttribute("action")).toBe("/safety-queue/action");
      expect(f.getAttribute("method")).toBe("post");
      const names = [...f.querySelectorAll("input")].map((i) => i.getAttribute("name"));
      expect(names.sort()).toEqual(["entry_id", "lang"]);
      expect(text(f.querySelector("button[type='submit']"))).toBe(c.acknowledge);
    }
  });

  it("an answered entry shows who and when, and no form", () => {
    const answered = doc.querySelector("tbody tr[data-entry][data-acknowledged='true']")!;
    expect(answered.querySelector("form")).toBeNull();
    expect(answered.querySelector("[data-col='acknowledged'] code")!.textContent).toBe(
      "sub-sentetik-klinik-sorumlusu",
    );
    expect(answered.querySelector("[data-col='acknowledged'] time")).not.toBeNull();
  });

  it("says plainly who may acknowledge, and that it takes one key", () => {
    expect(text(doc.querySelector("[data-tile='queue'] .window"))).toBe(c.whoMayAcknowledge);
  });

  it("the sidebar lists the page under Monitor and marks it current", () => {
    expect(CONSOLE_PAGES).toContain("safety-queue");
    expect(
      doc.querySelector("nav.console-nav [aria-current='page'][data-page-link='safety-queue']"),
    ).not.toBeNull();
  });

  it("near miss: nothing in the page echoes a submitted value or a patient word", () => {
    expect(html(queued())).not.toContain("style=");
    expect(html(queued(), "en")).not.toMatch(/Ayşe|hasta|patient said/i);
  });
});

describe("the empty queue and the result line", () => {
  it("an empty queue keeps the header and says what puts a row there", () => {
    const doc = dom(queued({ entries: [] }));
    expect(doc.querySelector("table thead th")).not.toBeNull();
    const empty = doc.querySelector("tr.empty-row [data-empty='safetyQueue']");
    expect(text(empty!.querySelector(".empty-title"))).toBe(EMPTIES.tr.safetyQueue.title);
    expect(text(doc.querySelector(".status-summary"))).toBe(
      `0 ${COPY.tr.summary.open} · 0 ${COPY.tr.summary.pastSla}`,
    );
  });

  it("a result code from the handler is shown as its sentence, never as the code's text", () => {
    const page = html(queued(), "tr", "safety_entry_already_acknowledged");
    expect(page).toContain('data-result="safety_entry_already_acknowledged"');
    expect(page).toContain(COPY.tr.results.safety_entry_already_acknowledged);
  });

  it("near miss: a value that is not a result code is not a result", () => {
    expect(isResultCode("<script>")).toBe(false);
    expect(isResultCode("acknowledged")).toBe(true);
  });
});

// --- the handler -----------------------------------------------------------------------

describe("the handler: nothing reaches the API that the API would refuse", () => {
  const ENTRY = "sx_" + "0123456789abcdef".repeat(2);

  it("plans one POST with no body to the entry's acknowledge route", () => {
    expect(planAcknowledge(form({ entry_id: ENTRY }))).toEqual({
      ok: true,
      path: `/admin/safety-queue/${ENTRY}/acknowledge`,
    });
  });

  it.each([["sx_short"], ["../../admin"], [""], ["SX_" + "A".repeat(32)]])(
    "refuses the entry id %j without dialling",
    (id) => {
      expect(planAcknowledge(form({ entry_id: id }))).toEqual({
        ok: false,
        code: "safety_entry_invalid",
      });
    },
  );

  async function submit(status: number, body: unknown, fetchSite = "same-origin") {
    const api = answering(status, body);
    const { code } = await submitAcknowledge({
      config: opsConfigFromEnv({ INTAKE_ADMIN_API_BASE: API }),
      authorization: BEARER,
      fetchSite,
      form: form({ entry_id: ENTRY }),
      fetch: api.fetch,
    });
    return { code, urls: api.urls, calls: api.calls };
  }

  it("refuses a cross-site post before anything is dialled", async () => {
    const { code, urls } = await submit(200, {}, "cross-site");
    expect(code).toBe("cross_site_refused");
    expect(urls).toEqual([]);
  });

  it("forwards the bearer, posts no body, and answers acknowledged on 200", async () => {
    const { code, urls, calls } = await submit(200, recorded().entries[4]);
    expect(code).toBe("acknowledged");
    expect(urls).toEqual([`${API}/admin/safety-queue/${ENTRY}/acknowledge`]);
    expect(calls[0]!.method).toBe("POST");
    expect(calls[0]!.body).toBeUndefined();
    expect((calls[0]!.headers as Record<string, string>)["authorization"]).toBe(BEARER);
  });

  it.each([
    [403, "forbidden"],
    [403, "tenant_required"],
    [404, "safety_entry_not_found"],
    [409, "safety_entry_already_acknowledged"],
    [503, "safety_inbox_unconfigured"],
    [503, "safety_inbox_unreachable"],
  ])("carries the API's %i %s back as a code", async (status, apiCode) => {
    const { code } = await submit(status, { error: apiCode });
    expect(code).toBe(apiCode);
  });

  it("near miss: the API's prose never becomes the code", async () => {
    const { code } = await submit(500, { error: "the store said: patient X is waiting" });
    expect(code).toBe("api_refused");
  });
});

// --- axe --------------------------------------------------------------------------------

describe("every state passes axe", () => {
  const states: [string, SafetyQueueState][] = [
    ["the queue", queued()],
    ["the empty queue", queued({ entries: [] })],
    ["the inbox unavailable", { kind: "inbox_unavailable", reason: "safety_inbox_unconfigured" }],
    ["refused", { kind: "not_admitted", reason: "no_credentials" }],
  ];
  for (const lang of ["tr", "en"] as const) {
    for (const [name, state] of states) {
      it(
        `${name} (${lang})`,
        async () => {
          expect(
            await violations(
              documentFor(createElement(SafetyQueueConsole, { state, lang, result: null }), lang),
            ),
          ).toEqual([]);
        },
        AXE_TIMEOUT_MS,
      );
    }
  }
});
