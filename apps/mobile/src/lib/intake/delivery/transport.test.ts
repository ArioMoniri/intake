/**
 * INT-587 — the one HTTP call that delivers a note: `PUT /v1/visits/{id}/note`
 * (services/api notes.write_note), proved against a fake fetcher.
 *
 * What the classification has to get right is which failures are worth a
 * retry. A dropped connection, a 5xx, a 408 or a 429 are; every other 4xx is
 * an answer, and retrying an answer forever is a phone hammering a server that
 * has already said no.
 */
import { describe, expect, it, vi } from "vitest";

import type { NotePutBody } from "./payload";
import { notePath, putNote, type Fetcher } from "./transport";

const BODY: NotePutBody = {
  sections: [{ id: "chief_complaint", title: "Başvuru nedeni", lines: ["Ağrı"] }],
  scopes: { chief_complaint: true },
  status: "sent",
};
const SERVER_VISIT = "0b6f6a52-0000-4000-8000-0000000000a1";

function respond(status: number, body: unknown, headers: Record<string, string> = {}): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: (name: string) => headers[name.toLowerCase()] ?? null },
    json: async () => body,
  } as unknown as Response;
}

function fetcher(response: Response | Error): Fetcher & ReturnType<typeof vi.fn> {
  return vi.fn(async () => {
    if (response instanceof Error) throw response;
    return response;
  }) as unknown as Fetcher & ReturnType<typeof vi.fn>;
}

describe("the request", () => {
  it("is a PUT of the JSON body to the visit's note path", async () => {
    const fetch = fetcher(respond(200, { status: "sent" }));
    await putNote(fetch, SERVER_VISIT, BODY);
    expect(fetch).toHaveBeenCalledTimes(1);
    const [path, init] = fetch.mock.calls[0] as [string, RequestInit];
    expect(path).toBe(`/v1/visits/${SERVER_VISIT}/note`);
    expect(init.method).toBe("PUT");
    expect(JSON.parse(String(init.body))).toEqual(BODY);
  });

  it("encodes the id, so nothing in it can reach another path", () => {
    expect(notePath("a/../b")).toBe("/v1/visits/a%2F..%2Fb/note");
  });
});

describe("only a confirmed send is a delivery", () => {
  it("a 200 whose body says sent is delivered", async () => {
    expect(await putNote(fetcher(respond(200, { status: "sent" })), SERVER_VISIT, BODY)).toEqual({
      kind: "delivered",
    });
  });

  it("a 200 that does not say sent is not a delivery — it is retried", async () => {
    // The near miss: the write landed but nothing confirms a share exists.
    // Treating it as delivered would let the app say "sent" on no evidence.
    for (const body of [{ status: "draft" }, null, "nonsense"]) {
      expect((await putNote(fetcher(respond(200, body)), SERVER_VISIT, BODY)).kind).toBe(
        "transient",
      );
    }
  });
});

describe("retryable failures", () => {
  it("a dropped connection is transient", async () => {
    expect(
      await putNote(fetcher(new TypeError("Network request failed")), SERVER_VISIT, BODY),
    ).toEqual({ kind: "transient", retryAfterMs: null });
  });

  it.each([500, 502, 503, 504, 408])("%i is transient", async (status) => {
    expect((await putNote(fetcher(respond(status, {})), SERVER_VISIT, BODY)).kind).toBe(
      "transient",
    );
  });

  it("429 carries the server's Retry-After in ms", async () => {
    expect(
      await putNote(fetcher(respond(429, {}, { "retry-after": "30" })), SERVER_VISIT, BODY),
    ).toEqual({ kind: "transient", retryAfterMs: 30_000 });
  });
});

describe("answers that are not retried on their own", () => {
  it("403 on the share scope asks the patient for consent", async () => {
    const response = respond(403, { error: "consent_required", scope: "share:previsit_note" });
    expect(await putNote(fetcher(response), SERVER_VISIT, BODY)).toEqual({ kind: "consent" });
  });

  it("403 on core is its own refusal — a different switch", async () => {
    const response = respond(403, { error: "consent_required", scope: "core" });
    expect(await putNote(fetcher(response), SERVER_VISIT, BODY)).toEqual({
      kind: "refused",
      reason: "core_consent",
    });
  });

  it("404 is not_found, 422 and 409 are invalid, 401 is session", async () => {
    expect(
      await putNote(fetcher(respond(404, { error: "not_found" })), SERVER_VISIT, BODY),
    ).toEqual({ kind: "refused", reason: "not_found" });
    expect(
      await putNote(fetcher(respond(422, { error: "validation_error" })), SERVER_VISIT, BODY),
    ).toEqual({ kind: "refused", reason: "invalid" });
    expect(await putNote(fetcher(respond(409, {})), SERVER_VISIT, BODY)).toEqual({
      kind: "refused",
      reason: "invalid",
    });
    expect(await putNote(fetcher(respond(401, {})), SERVER_VISIT, BODY)).toEqual({
      kind: "refused",
      reason: "session",
    });
  });

  it("any other 4xx is rejected", async () => {
    expect(await putNote(fetcher(respond(418, {})), SERVER_VISIT, BODY)).toEqual({
      kind: "refused",
      reason: "rejected",
    });
  });

  it("an auth error with no session is a session refusal, not a retry", async () => {
    const noSession = Object.assign(new Error("session"), { kind: "session" });
    expect(await putNote(fetcher(noSession), SERVER_VISIT, BODY)).toEqual({
      kind: "refused",
      reason: "session",
    });
  });
});
