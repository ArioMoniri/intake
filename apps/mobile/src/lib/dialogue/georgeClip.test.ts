/**
 * Dev-lane George (ElevenLabs) on-demand question clips — the CLIENT half of
 * ADR-028's on-demand variant. The device never holds the vendor key; this
 * client POSTs SCRIPTED question text to the dev server route and the server
 * reads the key from its env. Patient words never reach the vendor: a
 * `ScriptedTr` is only producible from an `IntakeQuestion` (catalog
 * composition), and `requireScriptedTr` refuses anything else.
 *
 * The generator is INJECTED here and no test dials a network (CLAUDE.md §How
 * we work): (a) cache miss → generator once → cached; (b) cache hit → generator
 * NOT called; (c) generator unavailable (server 503 / key absent) → fall back
 * to the self-hosted lane, no throw; (d) the scripted guard refuses non-scripted
 * (patient) text. INT-415: (e) every request names its delivery context
 * (routine by default) and never a voice setting; RED is never requested.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it, vi } from "vitest";

import { packForDepartment } from "../intake/questions";
import { DEFAULT_DELIVERY_CONTEXT, DELIVERY_CONTEXTS } from "./deliveryContext";
import {
  fetchGeorgeClip,
  fetchGeorgeClipVia,
  GEORGE_CLIP_PATH,
  GEORGE_MISSES,
  georgeMissForStatus,
  georgePreferringSynth,
  GeorgeUnavailable,
  requireScriptedTr,
  scriptedQuestionTr,
  type ClipLaneOutcome,
  type ScriptedTr,
} from "./georgeClip";
import { questionSpeechTr } from "./speech";
import { createClipStore, type ClipFs } from "./tts";

const cardio = packForDepartment("Kardiyoloji");
const question = cardio.find((q) => q.id === "duration")!;

function memFs(): ClipFs & { files: Map<string, string> } {
  const files = new Map<string, string>();
  return {
    files,
    async exists(path) {
      return files.has(path);
    },
    async mkdirp() {},
    async writeBase64(path, base64) {
      files.set(path, base64);
    },
    async removeDir(dir) {
      for (const key of [...files.keys()]) {
        if (key.startsWith(dir)) files.delete(key);
      }
    },
  };
}

describe("scripted-text guard (patient words never reach the generator)", () => {
  it("scriptedQuestionTr mints a ScriptedTr from a scripted question", () => {
    const scripted = scriptedQuestionTr(question);
    expect(scripted).toBe(questionSpeechTr(question));
  });

  it("requireScriptedTr accepts a question's own scripted composition", () => {
    const composed = questionSpeechTr(question);
    expect(requireScriptedTr(composed, question)).toBe(composed);
  });

  it("requireScriptedTr REFUSES text that is not the scripted composition", () => {
    // a patient-shaped answer — never equal to the catalog composition
    expect(() => requireScriptedTr("başım çok ağrıyor", question)).toThrow("george_not_scripted");
  });
});

describe("fetchGeorgeClip", () => {
  it("POSTs the scripted text_tr to the dev route and returns the bytes", async () => {
    const captured: { url?: string; body?: unknown } = {};
    const fetchImpl = vi.fn(async (url: string, init?: RequestInit) => {
      captured.url = url;
      captured.body = JSON.parse(String(init?.body));
      return new Response(new Uint8Array([1, 2, 3, 4]).buffer, { status: 200 });
    }) as unknown as typeof fetch;
    const scripted = scriptedQuestionTr(question);
    const bytes = await fetchGeorgeClip("http://dev.local:8000", scripted, { fetchImpl });
    expect(bytes).toEqual(new Uint8Array([1, 2, 3, 4]));
    expect(captured.url).toBe(`http://dev.local:8000${GEORGE_CLIP_PATH}`);
    // INT-415: no context given → the routine delivery profile, named on the wire
    expect(captured.body).toEqual({ text_tr: scripted, delivery_context: "routine" });
  });

  it("sends the utterance's delivery_context and nothing else about the voice", async () => {
    const bodies: unknown[] = [];
    const fetchImpl = vi.fn(async (_url: string, init?: RequestInit) => {
      bodies.push(JSON.parse(String(init?.body)));
      return new Response(new Uint8Array([1]).buffer, { status: 200 });
    }) as unknown as typeof fetch;
    const scripted = scriptedQuestionTr(question);
    for (const context of DELIVERY_CONTEXTS.filter((c) => c !== "red")) {
      await fetchGeorgeClip("http://dev.local:8000", scripted, { fetchImpl, context });
    }
    // the words are the same scripted composition every time; only the label
    // changes, and the voice settings stay server-side (never on the device)
    expect(bodies).toEqual(
      DELIVERY_CONTEXTS.filter((c) => c !== "red").map((context) => ({
        text_tr: scripted,
        delivery_context: context,
      })),
    );
  });

  it("never asks for a RED clip on demand — RED audio is pre-positioned (invariant 21)", async () => {
    const fetchImpl = vi.fn(async () => new Response(new Uint8Array([1]).buffer, { status: 200 }));
    const scripted = scriptedQuestionTr(question);
    await expect(
      fetchGeorgeClip("http://dev.local:8000", scripted, {
        fetchImpl: fetchImpl as unknown as typeof fetch,
        context: "red",
      }),
    ).rejects.toThrow("george_unavailable");
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("the default context is the shared contract's routine", () => {
    expect(DEFAULT_DELIVERY_CONTEXT).toBe("routine");
    expect(DELIVERY_CONTEXTS).toEqual([
      "welcome",
      "routine",
      "sensitive",
      "instrument",
      "acknowledgement",
      "red",
      "closing",
    ]);
  });

  it("throws george_unavailable on a non-2xx (server 503 / key absent)", async () => {
    const fetchImpl = vi.fn(
      async () => new Response("", { status: 503 }),
    ) as unknown as typeof fetch;
    const scripted = scriptedQuestionTr(question);
    await expect(fetchGeorgeClip("http://dev.local:8000", scripted, { fetchImpl })).rejects.toThrow(
      "george_unavailable",
    );
  });
});

describe("georgePreferringSynth + clip store", () => {
  const scripted = scriptedQuestionTr(question) as ScriptedTr;

  it("(a) cache miss → George generator called ONCE, clip cached", async () => {
    const george = vi.fn(async () => new Uint8Array([9, 9, 9]));
    const fallback = vi.fn(async () => new Uint8Array([0]));
    const fs = memFs();
    const store = createClipStore("/clips/", fs, (t) =>
      georgePreferringSynth(george, fallback)(t as ScriptedTr),
    );
    await store.ensure("q_duration.wav", scripted);
    expect(george).toHaveBeenCalledTimes(1);
    expect(fallback).not.toHaveBeenCalled();
    expect(fs.files.has("/clips/q_duration.wav")).toBe(true);
  });

  it("(b) cache hit → George generator NOT called again", async () => {
    const george = vi.fn(async () => new Uint8Array([9, 9, 9]));
    const fallback = vi.fn(async () => new Uint8Array([0]));
    const fs = memFs();
    const store = createClipStore("/clips/", fs, (t) =>
      georgePreferringSynth(george, fallback)(t as ScriptedTr),
    );
    await store.ensure("q_duration.wav", scripted);
    await store.ensure("q_duration.wav", scripted);
    expect(george).toHaveBeenCalledTimes(1);
  });

  it("(c) George unavailable → falls back to the self-hosted lane, no throw", async () => {
    const george = vi.fn(async () => {
      throw new Error("george_unavailable");
    });
    const fallback = vi.fn(async () => new Uint8Array([7]));
    const bytes = await georgePreferringSynth(george, fallback)(scripted);
    expect(bytes).toEqual(new Uint8Array([7]));
    expect(george).toHaveBeenCalledTimes(1);
    expect(fallback).toHaveBeenCalledTimes(1);
  });

  it("forwards the utterance's context to George, routine when none is given", async () => {
    const george = vi.fn(async () => new Uint8Array([9]));
    const fallback = vi.fn(async () => new Uint8Array([0]));
    const synth = georgePreferringSynth(george, fallback);
    await synth(scripted);
    await synth(scripted, "sensitive");
    expect(george).toHaveBeenNthCalledWith(1, scripted, "routine");
    expect(george).toHaveBeenNthCalledWith(2, scripted, "sensitive");
    expect(fallback).not.toHaveBeenCalled();
  });

  it("no George source (null) uses the self-hosted lane directly", async () => {
    const fallback = vi.fn(async () => new Uint8Array([5]));
    const bytes = await georgePreferringSynth(null, fallback)(scripted);
    expect(bytes).toEqual(new Uint8Array([5]));
    expect(fallback).toHaveBeenCalledTimes(1);
  });
});

// ---------------------------------------------------------------------------
// INT-440 — the owner heard a robotic voice because George never served, and
// nothing said so. Since INT-326 the route requires an authenticated patient;
// the client posted anonymously, got a 401, and `georgePreferringSynth`
// swallowed it. The request now rides an injected (authenticated) transport,
// every miss carries a closed-set reason, and the synthesizer reports which
// lane actually served each clip.
// ---------------------------------------------------------------------------

describe("fetchGeorgeClipVia — the request rides the caller's transport (INT-440)", () => {
  const scripted = scriptedQuestionTr(question);

  it("hands the transport the route PATH and the scripted body — no base, no key", async () => {
    const calls: { path: string; init: RequestInit }[] = [];
    const transport = vi.fn(async (path: string, init: RequestInit) => {
      calls.push({ path, init });
      return new Response(new Uint8Array([1, 2]).buffer, { status: 200 });
    });
    const bytes = await fetchGeorgeClipVia(transport, scripted);
    expect(bytes).toEqual(new Uint8Array([1, 2]));
    expect(calls).toHaveLength(1);
    expect(calls[0].path).toBe(GEORGE_CLIP_PATH);
    expect(calls[0].init.method).toBe("POST");
    expect(JSON.parse(String(calls[0].init.body))).toEqual({
      text_tr: scripted,
      delivery_context: "routine",
    });
  });

  it.each([
    [401, "unauthorized"],
    [403, "unauthorized"],
    [404, "not_mounted"],
    [422, "refused"],
    [429, "rate_limited"],
    [502, "vendor"],
    [503, "unconfigured"],
    [500, "status"],
  ] as const)(
    "names a %i as %s, still george_unavailable to the caller",
    async (status, reason) => {
      const transport = async () => new Response("", { status });
      const error = await fetchGeorgeClipVia(transport, scripted).catch((e: unknown) => e);
      expect(error).toBeInstanceOf(GeorgeUnavailable);
      expect((error as GeorgeUnavailable).message).toBe("george_unavailable");
      expect((error as GeorgeUnavailable).reason).toBe(reason);
      expect(georgeMissForStatus(status)).toBe(reason);
    },
  );

  it("passes a transport's own reason through (no session, no host)", async () => {
    const transport = async (): Promise<Response> => {
      throw new GeorgeUnavailable("no_session");
    };
    const error = await fetchGeorgeClipVia(transport, scripted).catch((e: unknown) => e);
    expect((error as GeorgeUnavailable).reason).toBe("no_session");
  });

  it("names any other transport error 'transport' and never echoes it", async () => {
    const transport = async (): Promise<Response> => {
      throw new Error("connect ECONNREFUSED 10.0.0.9:8000");
    };
    const error = await fetchGeorgeClipVia(transport, scripted).catch((e: unknown) => e);
    expect((error as GeorgeUnavailable).reason).toBe("transport");
    expect(String((error as Error).message)).not.toContain("10.0.0.9");
  });

  it("names a client-side give-up 'timeout'", async () => {
    const transport = (_path: string, init: RequestInit) =>
      new Promise<Response>((_resolve, reject) => {
        init.signal?.addEventListener("abort", () => reject(new Error("aborted")));
      });
    const error = await fetchGeorgeClipVia(transport, scripted, { timeoutMs: 5 }).catch(
      (e: unknown) => e,
    );
    expect((error as GeorgeUnavailable).reason).toBe("timeout");
  });

  it("names an empty 2xx body 'empty'", async () => {
    const transport = async () => new Response(new Uint8Array([]).buffer, { status: 200 });
    const error = await fetchGeorgeClipVia(transport, scripted).catch((e: unknown) => e);
    expect((error as GeorgeUnavailable).reason).toBe("empty");
  });

  it("every reason is a member of the closed set the banner and metric label use", () => {
    for (const status of [400, 401, 403, 404, 422, 429, 500, 502, 503, 504]) {
      expect(GEORGE_MISSES).toContain(georgeMissForStatus(status));
    }
  });
});

describe("georgePreferringSynth reports which lane served the clip (INT-440)", () => {
  const scripted = scriptedQuestionTr(question) as ScriptedTr;

  it("George served → one 'george' outcome", async () => {
    const outcomes: ClipLaneOutcome[] = [];
    const synth = georgePreferringSynth(
      async () => new Uint8Array([9]),
      async () => new Uint8Array([0]),
      (outcome) => outcomes.push(outcome),
    );
    await synth(scripted);
    expect(outcomes).toEqual([{ lane: "george" }]);
  });

  it("a George miss is never silent: the fallback outcome names the reason", async () => {
    const outcomes: ClipLaneOutcome[] = [];
    const synth = georgePreferringSynth(
      async () => {
        throw new GeorgeUnavailable("unauthorized");
      },
      async () => new Uint8Array([0]),
      (outcome) => outcomes.push(outcome),
    );
    await synth(scripted);
    expect(outcomes).toEqual([{ lane: "self_hosted", georgeMiss: "unauthorized" }]);
  });

  it("no George source at all is reported as 'off'", async () => {
    const outcomes: ClipLaneOutcome[] = [];
    await georgePreferringSynth(
      null,
      async () => new Uint8Array([0]),
      (outcome) => outcomes.push(outcome),
    )(scripted);
    expect(outcomes).toEqual([{ lane: "self_hosted", georgeMiss: "off" }]);
  });

  it("an unexpected George error is reported as 'transport'", async () => {
    const outcomes: ClipLaneOutcome[] = [];
    await georgePreferringSynth(
      async () => {
        throw new Error("boom");
      },
      async () => new Uint8Array([0]),
      (outcome) => outcomes.push(outcome),
    )(scripted);
    expect(outcomes).toEqual([{ lane: "self_hosted", georgeMiss: "transport" }]);
  });

  it("reports nothing when no lane produced a clip", async () => {
    const outcomes: ClipLaneOutcome[] = [];
    const synth = georgePreferringSynth(
      null,
      async () => {
        throw new Error("tts_unreachable");
      },
      (outcome) => outcomes.push(outcome),
    );
    await expect(synth(scripted)).rejects.toThrow("tts_unreachable");
    expect(outcomes).toEqual([]);
  });
});

describe("the device's George source authenticates (INT-440)", () => {
  const clipsSource = readFileSync(
    join(fileURLToPath(new URL(".", import.meta.url)), "clips.ts"),
    "utf8",
  );

  it("posts through the DPoP-bound authedFetch, never an anonymous fetch", () => {
    expect(clipsSource).toMatch(/import \{[^}]*\bauthedFetch\b[^}]*\} from "\.\.\/auth\/api"/);
    expect(clipsSource).toContain("fetchGeorgeClipVia(");
    // the anonymous base+fetch entry point is what returned 401 since INT-326
    expect(clipsSource).not.toMatch(/\bfetchGeorgeClip\(/);
  });
});
