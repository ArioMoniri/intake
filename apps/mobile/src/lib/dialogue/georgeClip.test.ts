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
import { describe, expect, it, vi } from "vitest";

import { packForDepartment } from "../intake/questions";
import { DEFAULT_DELIVERY_CONTEXT, DELIVERY_CONTEXTS } from "./deliveryContext";
import {
  fetchGeorgeClip,
  GEORGE_CLIP_PATH,
  georgePreferringSynth,
  requireScriptedTr,
  scriptedQuestionTr,
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
