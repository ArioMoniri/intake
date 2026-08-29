/**
 * INT-199 extract client: the wire is NEVER trusted. Every response is
 * re-validated against the pack (unknown question ids and option ids are
 * dropped; single-select must carry exactly one value), and every failure
 * mode (503, network, abort, malformed body) becomes a typed failure the
 * screen can turn into the manual fallback.
 */
import { describe, expect, it } from "vitest";

import { reachableBaseUrl, serviceCandidates } from "./dev/hosts";
import {
  TRANSCRIPT_MAX_CHARS,
  requestExtract,
  toQuestionSpecs,
  validateExtractResponse,
  type ExtractQuestionSpec,
} from "./extract";
import { packForDepartment } from "./intake/questions";

const cardio = packForDepartment("Kardiyoloji");
const specs = toQuestionSpecs(cardio);

function spec(id: string): ExtractQuestionSpec {
  const found = specs.find((s) => s.id === id);
  if (!found) {
    throw new Error(`fixture question missing: ${id}`);
  }
  return found;
}

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("shared dev-lane host probing (generalised from voice.ts)", () => {
  it("builds candidates from the Metro host first, then extras, deduped, on the given port", () => {
    expect(serviceCandidates("192.168.1.7:8081", ["127.0.0.1", "192.168.1.7"], 8804)).toEqual([
      "http://192.168.1.7:8804",
      "http://127.0.0.1:8804",
    ]);
  });

  it("skips exp.direct tunnel hosts (no route back to the dev Mac)", () => {
    expect(serviceCandidates("abc-123.exp.direct:80", ["127.0.0.1"], 8802)).toEqual([
      "http://127.0.0.1:8802",
    ]);
  });

  it("keeps the ASR port and the extract port as plain parameters", () => {
    expect(serviceCandidates(undefined, ["127.0.0.1"], 8802)).toEqual(["http://127.0.0.1:8802"]);
    expect(serviceCandidates(undefined, ["127.0.0.1"], 8804)).toEqual(["http://127.0.0.1:8804"]);
  });

  it("reachableBaseUrl returns the first candidate whose /health answers", async () => {
    const fetchImpl: typeof fetch = async (url) => {
      if (String(url).startsWith("http://10.0.0.9:8804")) {
        throw new TypeError("Network request failed");
      }
      return jsonResponse(200, { status: "ok" });
    };
    const base = await reachableBaseUrl(["http://10.0.0.9:8804", "http://127.0.0.1:8804"], {
      fetchImpl,
    });
    expect(base).toBe("http://127.0.0.1:8804");
  });

  it("reachableBaseUrl returns null when nothing answers", async () => {
    const fetchImpl: typeof fetch = async () => {
      throw new TypeError("Network request failed");
    };
    expect(await reachableBaseUrl(["http://127.0.0.1:8804"], { fetchImpl })).toBeNull();
  });
});

describe("toQuestionSpecs", () => {
  it("maps the cardio pack: option ids for chips/single, null for text", () => {
    // INT-198 grew the cardio pack to full OLDCARTS depth; INT-239 added
    // the answer-gated follow-ups. Extraction covers the WHOLE pack, gated
    // questions included: the patient may volunteer a detail before its
    // gate opens, and the suggestion then waits for the gate rather than
    // being thrown away.
    expect(specs.map((s) => s.id)).toEqual([
      "complaint",
      "duration",
      "onset",
      "pain_character",
      "radiation",
      "radiation_side",
      "breath_timing",
      "breath_lying",
      "trigger",
      "associated",
      "cardio_palpitation",
      "severity",
      "extra",
    ]);
    expect(spec("complaint").kind).toBe("chips");
    expect(spec("complaint").options).toContain("pain");
    expect(spec("duration").kind).toBe("single");
    expect(spec("duration").options).toEqual(["today", "days", "week", "month"]);
    expect(spec("extra").kind).toBe("text");
    expect(spec("extra").options).toBeNull();
  });
});

describe("validateExtractResponse (client mirrors the server rules)", () => {
  it("accepts a well-formed response for the cardio pack", () => {
    const result = validateExtractResponse(
      {
        candidates: {
          complaint: {
            values: ["pain", "dyspnoea"],
            quote: "Göğsümde baskı var, nefesim daralıyor",
          },
          duration: { values: ["days"], quote: "birkaç gündür böyle" },
          extra: { values: ["Merdiven çıkarken artıyor"], quote: "merdiven çıkarken artıyor" },
        },
        dropped: ["blood_pressure"],
        model: "qwen3.5-9b",
      },
      specs,
    );
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(Object.keys(result.candidates).sort()).toEqual(["complaint", "duration", "extra"]);
      expect(result.candidates.complaint.values).toEqual(["pain", "dyspnoea"]);
      expect(result.candidates.duration.quote).toBe("birkaç gündür böyle");
      expect(result.dropped).toEqual(["blood_pressure"]);
      expect(result.model).toBe("qwen3.5-9b");
    }
  });

  it("drops candidates for question ids not in the pack", () => {
    // neuro_character is a real question id from ANOTHER pack — cross-pack
    // ids must be dropped exactly like invented ones.
    const result = validateExtractResponse(
      {
        candidates: { neuro_character: { values: ["throbbing"], quote: "zonkluyor" } },
        dropped: [],
        model: "m",
      },
      specs,
    );
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.candidates).toEqual({});
    }
  });

  it("filters unknown option ids and keeps the survivors, deduped", () => {
    const result = validateExtractResponse(
      {
        candidates: {
          complaint: { values: ["pain", "made_up", "pain", "fever"], quote: "ağrım ve ateşim var" },
        },
        dropped: [],
        model: "m",
      },
      specs,
    );
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.candidates.complaint.values).toEqual(["pain", "fever"]);
    }
  });

  it("drops a chips candidate whose values are all unknown", () => {
    const result = validateExtractResponse(
      {
        candidates: { complaint: { values: ["made_up"], quote: "…" } },
        dropped: [],
        model: "m",
      },
      specs,
    );
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.candidates.complaint).toBeUndefined();
    }
  });

  it("single = exactly one value: a two-value single candidate is dropped, never guessed", () => {
    const result = validateExtractResponse(
      {
        candidates: {
          duration: { values: ["days", "week"], quote: "birkaç gündür, belki bir haftadır" },
        },
        dropped: [],
        model: "m",
      },
      specs,
    );
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.candidates.duration).toBeUndefined();
    }
  });

  it("a single candidate whose one value survives filtering is kept", () => {
    const result = validateExtractResponse(
      {
        candidates: { duration: { values: ["days", "days"], quote: "birkaç gündür" } },
        dropped: [],
        model: "m",
      },
      specs,
    );
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.candidates.duration?.values).toEqual(["days"]);
    }
  });

  it("free-text candidates keep non-empty trimmed strings only", () => {
    const result = validateExtractResponse(
      {
        candidates: { extra: { values: ["  ", "Merdiven çıkarken artıyor  ", 42], quote: "q" } },
        dropped: [],
        model: "m",
      },
      specs,
    );
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.candidates.extra?.values).toEqual(["Merdiven çıkarken artıyor"]);
    }
  });

  it("drops malformed candidates: missing quote, non-array values, non-object entries", () => {
    const result = validateExtractResponse(
      {
        candidates: {
          complaint: { values: ["pain"] },
          duration: { values: "days", quote: "q" },
          extra: "not an object",
        },
        dropped: [],
        model: "m",
      },
      specs,
    );
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.candidates).toEqual({});
    }
  });

  it("rejects a malformed envelope outright", () => {
    for (const raw of [null, [], "x", 7, {}, { candidates: [] }, { candidates: "x" }]) {
      const result = validateExtractResponse(raw, specs);
      expect(result.ok).toBe(false);
      if (!result.ok) {
        expect(result.reason).toBe("invalid_response");
      }
    }
  });

  it("tolerates a missing dropped list and keeps only string entries", () => {
    const noDropped = validateExtractResponse({ candidates: {}, model: "m" }, specs);
    expect(noDropped.ok).toBe(true);
    if (noDropped.ok) {
      expect(noDropped.dropped).toEqual([]);
    }
    const mixed = validateExtractResponse(
      { candidates: {}, dropped: ["a", 3, null], model: "m" },
      specs,
    );
    expect(mixed.ok).toBe(true);
    if (mixed.ok) {
      expect(mixed.dropped).toEqual(["a"]);
    }
  });
});

describe("requestExtract wire behaviour", () => {
  const validBody = {
    candidates: { duration: { values: ["days"], quote: "birkaç gündür" } },
    dropped: [],
    model: "qwen3.5-9b",
  };

  it("POSTs the pack payload and returns validated candidates on 200", async () => {
    let captured: { url: string; body: unknown } | null = null;
    const fetchImpl: typeof fetch = async (url, init) => {
      captured = { url: String(url), body: JSON.parse(String(init?.body)) };
      return jsonResponse(200, validBody);
    };
    const result = await requestExtract(
      "http://127.0.0.1:8804",
      "birkaç gündür göğsümde baskı var",
      "Kardiyoloji",
      specs,
      { fetchImpl },
    );
    expect(result).toEqual({
      ok: true,
      candidates: { duration: { values: ["days"], quote: "birkaç gündür" } },
      dropped: [],
      model: "qwen3.5-9b",
    });
    expect(captured!.url).toBe("http://127.0.0.1:8804/extract");
    expect(captured!.body).toMatchObject({
      transcript: "birkaç gündür göğsümde baskı var",
      pack: "Kardiyoloji",
    });
    expect((captured!.body as { questions: unknown[] }).questions).toHaveLength(specs.length);
  });

  it("truncates the transcript to the server cap before sending", async () => {
    let sent = "";
    const fetchImpl: typeof fetch = async (_url, init) => {
      sent = (JSON.parse(String(init?.body)) as { transcript: string }).transcript;
      return jsonResponse(200, validBody);
    };
    await requestExtract(
      "http://127.0.0.1:8804",
      "a".repeat(TRANSCRIPT_MAX_CHARS + 50),
      "general",
      specs,
      { fetchImpl },
    );
    expect(sent).toHaveLength(TRANSCRIPT_MAX_CHARS);
  });

  it("503 → typed 'unavailable' failure (manual fallback)", async () => {
    const fetchImpl: typeof fetch = async () => jsonResponse(503, { error: "extract_unavailable" });
    const result = await requestExtract("http://127.0.0.1:8804", "t", "general", specs, {
      fetchImpl,
    });
    expect(result).toEqual({ ok: false, reason: "unavailable" });
  });

  it("network failure → typed 'unreachable' failure", async () => {
    const fetchImpl: typeof fetch = async () => {
      throw new TypeError("Network request failed");
    };
    const result = await requestExtract("http://127.0.0.1:8804", "t", "general", specs, {
      fetchImpl,
    });
    expect(result).toEqual({ ok: false, reason: "unreachable" });
  });

  it("a 200 with a non-JSON body → 'invalid_response'", async () => {
    const fetchImpl: typeof fetch = async () => new Response("not json", { status: 200 });
    const result = await requestExtract("http://127.0.0.1:8804", "t", "general", specs, {
      fetchImpl,
    });
    expect(result).toEqual({ ok: false, reason: "invalid_response" });
  });

  it("an already-aborted signal short-circuits without touching the network", async () => {
    let called = false;
    const fetchImpl: typeof fetch = async () => {
      called = true;
      return jsonResponse(200, validBody);
    };
    const controller = new AbortController();
    controller.abort();
    const result = await requestExtract("http://127.0.0.1:8804", "t", "general", specs, {
      signal: controller.signal,
      fetchImpl,
    });
    expect(result).toEqual({ ok: false, reason: "aborted" });
    expect(called).toBe(false);
  });

  it("cancelling mid-flight → typed 'aborted' failure (the waiting state is cancellable)", async () => {
    const fetchImpl: typeof fetch = (_url, init) =>
      new Promise((_resolve, reject) => {
        init?.signal?.addEventListener("abort", () =>
          reject(new DOMException("Aborted", "AbortError")),
        );
      });
    const controller = new AbortController();
    const pending = requestExtract("http://127.0.0.1:8804", "t", "general", specs, {
      signal: controller.signal,
      fetchImpl,
    });
    controller.abort();
    expect(await pending).toEqual({ ok: false, reason: "aborted" });
  });
});
