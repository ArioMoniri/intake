/**
 * INT-559 — the app's voice lane never writes patient audio to a file
 * (CLAUDE.md invariant 3, with no dev exception).
 *
 * Before this change the DEV voice lane (useDialogueSession.ts) and the
 * VoiceNote pill recorded through expo-audio's file recorder and deleted the
 * file after upload. Now the microphone is a PCM stream into a bounded
 * in-memory buffer (≤ 60 s), handed to the ASR client as bytes, and zeroed on
 * finish, discard, RED, leave and app background. There is no React Native
 * render test in this app, so — as in voice.spec.ts and bargeIn.spec.ts — the
 * repository facts are pinned on the source, and the behaviour of the pure
 * modules is driven in node with a storage trap on the globals.
 */
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { MAX_CAPTURE_SECONDS } from "../src/lib/capture/boundedBuffer";
import { createCaptureTurn } from "../src/lib/capture/turn";
import type { PcmChunk, PcmSegment, PcmStreamPort } from "../src/lib/capture/types";

const MOBILE = join(__dirname, "..");
const SRC = join(MOBILE, "src");
const CAPTURE_DIR = join(SRC, "lib", "capture");

const read = (...segments: string[]) => readFileSync(join(...segments), "utf8");

/** Code only, comments dropped — the comments here NAME what must not happen. */
function code(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
}

/** Every production module of the capture library. */
function captureSources(): { name: string; source: string }[] {
  return readdirSync(CAPTURE_DIR)
    .filter((name) => name.endsWith(".ts") && !name.endsWith(".test.ts"))
    .map((name) => ({ name: `lib/capture/${name}`, source: read(CAPTURE_DIR, name) }));
}

/** The whole patient-audio path: the library plus every file that drives it. */
function pathSources(): { name: string; source: string }[] {
  return [
    ...captureSources(),
    { name: "lib/voice.ts", source: read(SRC, "lib", "voice.ts") },
    {
      name: "lib/dialogue/useDialogueSession.ts",
      source: read(SRC, "lib", "dialogue", "useDialogueSession.ts"),
    },
    { name: "components/VoiceNote.tsx", source: read(SRC, "components", "VoiceNote.tsx") },
  ];
}

const HOOK = read(SRC, "lib", "dialogue", "useDialogueSession.ts");
const VOICE_NOTE = read(SRC, "components", "VoiceNote.tsx");
const VOICE = read(SRC, "lib", "voice.ts");
const INTAKE = read(SRC, "app", "(tabs)", "visits", "[visitId]", "intake.tsx");

/** The capture modules that must stay pure: no expo, no react-native, no node. */
const PURE = [
  "boundedBuffer.ts",
  "level.ts",
  "envelope.ts",
  "session.ts",
  "turn.ts",
  "microphone.ts",
  "policy.ts",
  "asrClient.ts",
  "types.ts",
];

describe("invariant 3: nothing on the patient-audio path can reach a file", () => {
  it("scans a real corpus (the gate is hollow if it finds nothing)", () => {
    const names = pathSources().map((s) => s.name);
    expect(names.length).toBeGreaterThanOrEqual(12);
    for (const required of [
      "lib/capture/session.ts",
      "lib/capture/turn.ts",
      "lib/capture/expoStream.ts",
      "lib/capture/asrClient.ts",
      "lib/voice.ts",
      "lib/dialogue/useDialogueSession.ts",
      "components/VoiceNote.tsx",
    ]) {
      expect(names).toContain(required);
    }
  });

  it("imports no filesystem or storage module, and calls no file API", () => {
    const forbidden = [
      "expo-file-system",
      "expo-sqlite",
      "expo-secure-store",
      "@react-native-async-storage",
      "node:fs",
      'from "fs"',
      "react-native-fs",
      "expo-media-library",
      "FileSystem",
      "uploadAsync",
      "writeAsStringAsync",
      "deleteAsync",
      "cacheDirectory",
      "documentDirectory",
      "Paths.",
      "new File(",
      "new Directory(",
      "localStorage",
    ];
    for (const { name, source } of pathSources()) {
      const body = code(source);
      for (const token of forbidden) {
        expect(body, `${name} must not reach for ${token}`).not.toContain(token);
      }
    }
  });

  it("names no audio artefact and no recorder API", () => {
    const audioExtensions = /\.(wav|mp3|ogg|oga|opus|flac|m4a|aac|pcm|amr|aiff|caf|webm)\b/i;
    for (const { name, source } of pathSources()) {
      const body = code(source);
      expect(body, `${name} names an audio artefact`).not.toMatch(audioExtensions);
      expect(body, `${name} reaches for a recorder`).not.toMatch(/recorder/i);
      for (const api of [
        "prepareToRecordAsync",
        "RecordingPresets",
        "getStatus(",
        "MediaRecorder",
      ]) {
        expect(body, `${name} reaches for ${api}`).not.toContain(api);
      }
    }
  });

  it("the native stream sits behind one lazy import, in one file", () => {
    const binding = read(CAPTURE_DIR, "expoStream.ts");
    expect(code(binding)).toContain('await import("expo-audio")');
    expect(code(binding)).not.toMatch(/from\s+"expo-audio"/);
    for (const { name, source } of captureSources()) {
      if (name.endsWith("expoStream.ts")) {
        continue;
      }
      expect(code(source), `${name} must not touch the native stream`).not.toContain("AudioStream");
      expect(code(source), `${name} must not import expo-audio`).not.toContain("expo-audio");
    }
  });

  it("the pure modules import nothing from expo, react or the platform", () => {
    for (const name of PURE) {
      const body = code(read(CAPTURE_DIR, name));
      const specifiers = [...body.matchAll(/from\s+"([^"]+)"/g)].map((m) => m[1]);
      for (const specifier of specifiers) {
        expect(specifier, `${name} imports ${specifier}`).toMatch(/^\.\//);
      }
      expect(body).not.toContain("import(");
    }
  });

  it("the buffer is bounded at sixty seconds and the session sizes from the cap", () => {
    expect(MAX_CAPTURE_SECONDS).toBe(60);
    const session = code(read(CAPTURE_DIR, "session.ts"));
    expect(session).toContain("capacityFor(");
    expect(session).toContain("MAX_CAPTURE_SECONDS");
  });
});

describe("invariant 3: the buffer is zeroed on every trigger (driven in node)", () => {
  interface Fake {
    port: PcmStreamPort;
    calls: string[];
    emitSeconds(seconds: number): void;
  }

  function fakeStream(): Fake {
    const listeners = new Set<(chunk: PcmChunk) => void>();
    const calls: string[] = [];
    const rate = 1_000;
    return {
      calls,
      port: {
        start: async () => {
          calls.push("start");
        },
        stop: () => {
          calls.push("stop");
        },
        onBuffer: (listener) => {
          listeners.add(listener);
          return () => listeners.delete(listener);
        },
      },
      emitSeconds(seconds) {
        const samples = new Int16Array(Math.round(seconds * rate)).fill(1_000);
        for (const listener of listeners) {
          listener({ data: samples.buffer as ArrayBuffer, sampleRate: rate, channels: 1 });
        }
      },
    };
  }

  /** Any reach for a storage-shaped global during the turn is recorded. */
  async function withStorageTrap(run: () => Promise<void>): Promise<string[]> {
    const touched: string[] = [];
    const trap = new Proxy(
      {},
      {
        get: (_target, property) => {
          touched.push(String(property));
          return () => undefined;
        },
      },
    );
    const globals = globalThis as unknown as Record<string, unknown>;
    const restored = { localStorage: globals.localStorage, FileReader: globals.FileReader };
    globals.localStorage = trap;
    globals.FileReader = trap;
    try {
      await run();
    } finally {
      globals.localStorage = restored.localStorage;
      globals.FileReader = restored.FileReader;
    }
    return touched;
  }

  it("a seventy-second answer is two in-memory segments, never more than sixty seconds held", async () => {
    const fake = fakeStream();
    const handed: PcmSegment[] = [];
    let closed = false;
    const turn = createCaptureTurn({
      createStream: async () => fake.port,
      transcribe: async (segment) => {
        handed.push({ ...segment, samples: Int16Array.from(segment.samples) });
        return `part${handed.length}`;
      },
      closed: () => closed,
    });
    const touched = await withStorageTrap(async () => {
      expect(await turn.open()).toBe(true);
      for (let second = 0; second < 70; second += 1) {
        fake.emitSeconds(1);
      }
      expect(await turn.finish()).toBe("part1 part2");
      closed = true;
    });
    expect(touched).toEqual([]);
    expect(handed.map((segment) => segment.samples.length)).toEqual([60_000, 10_000]);
    expect(turn.zeroed()).toBe(true);
    expect(turn.capturing).toBe(false);
    expect(fake.calls).toEqual(["start", "stop"]);
  });

  it("a RED or a background closes the microphone and zeroes without a single byte leaving", async () => {
    const fake = fakeStream();
    let sent = 0;
    const turn = createCaptureTurn({
      createStream: async () => fake.port,
      transcribe: async () => {
        sent += 1;
        return "";
      },
      closed: () => false,
    });
    const touched = await withStorageTrap(async () => {
      await turn.open();
      fake.emitSeconds(30);
      turn.discard();
    });
    expect(touched).toEqual([]);
    expect(sent).toBe(0);
    expect(turn.zeroed()).toBe(true);
    expect(fake.calls).toEqual(["start", "stop"]);
  });

  it("a prepare that is abandoned leaves nothing: closed before start means no stream at all", async () => {
    const fake = fakeStream();
    const turn = createCaptureTurn({
      createStream: async () => fake.port,
      transcribe: async () => "",
      closed: () => true,
    });
    expect(await turn.open()).toBe(false);
    expect(fake.calls).toEqual([]);
    expect(await turn.finish()).toBeNull();
  });
});

describe("the dialogue and the pill drive the capture, and close it on every trigger", () => {
  it("the dialogue's leave closes the microphone before it awaits anything (RED path, invariant 9/21)", () => {
    const body = code(HOOK);
    const leave = body.slice(body.indexOf("const leave = async () => {"));
    const beforeFirstAwait = leave.slice(0, leave.indexOf("await "));
    expect(beforeFirstAwait).toContain("closedRef.current = true");
    expect(beforeFirstAwait).toContain("discardCapture()");
  });

  it("the dialogue discards on failure, on unmount and when a typed message abandons a listen", () => {
    const body = code(HOOK);
    const failed = body.slice(
      body.indexOf('phase === "failed"'),
      body.indexOf('phase === "handoff"'),
    );
    expect(failed).toContain("discardCapture()");
    const unmount = body.slice(
      body.indexOf("onHandoff(stateRef.current.pending)"),
      body.indexOf("useAppStateChange("),
    );
    expect(unmount).toContain("discardCapture()");
    const typed = body.slice(body.indexOf("const sendTyped"), body.indexOf("const bargeIn"));
    expect(typed).toContain("discardCapture()");
  });

  it("the dialogue's unmount closes the session before it discards (INT-559 review of #964, B2)", () => {
    // Without the close, a driver that resumes past an await after the
    // unmount opens a microphone no one owns (microphone.test.ts drives it).
    const body = code(HOOK);
    const unmount = body.slice(
      body.indexOf("onHandoff(stateRef.current.pending)"),
      body.indexOf("useAppStateChange("),
    );
    const closes = unmount.indexOf("closedRef.current = true");
    expect(closes).toBeGreaterThanOrEqual(0);
    expect(closes).toBeLessThan(unmount.indexOf("discardCapture()"));
  });

  it("the dialogue and the pill open through one microphone, so a discard reaches an open in flight", () => {
    // The capture turn is made inside the microphone's factory and nowhere
    // else: a turn made outside it would be one a discard cannot reach while
    // the audio session is still being prepared.
    for (const [name, source] of [
      ["lib/dialogue/useDialogueSession.ts", HOOK],
      ["components/VoiceNote.tsx", VOICE_NOTE],
    ] as const) {
      const body = code(source);
      expect(body, name).toContain("createMicrophone(");
      expect(body.split("createCaptureTurn(").length - 1, name).toBe(1);
      const factory = body.slice(body.indexOf("createMicrophone("));
      const turnAt = factory.indexOf("createCaptureTurn(");
      expect(turnAt, name).toBeGreaterThan(0);
      expect(turnAt, name).toBeLessThan(factory.indexOf("closedRef.current"));
    }
    const discard = code(HOOK).slice(code(HOOK).indexOf("const discardCapture = "));
    expect(discard.slice(0, discard.indexOf(";"))).toContain(".discard()");
  });

  it("the dialogue and the pill both zero on app background", () => {
    expect(code(HOOK)).toContain("useAppStateChange(");
    expect(code(VOICE_NOTE)).toContain("useAppStateChange(");
    const hookListener = code(HOOK).slice(code(HOOK).indexOf("useAppStateChange("));
    expect(hookListener.slice(0, 600)).toContain("discardCapture()");
    const pillListener = code(VOICE_NOTE).slice(code(VOICE_NOTE).indexOf("useAppStateChange("));
    expect(pillListener.slice(0, 400)).toContain("discard()");
  });

  it("the pill discards on unmount and transcribes from the turn, never from a path", () => {
    const body = code(VOICE_NOTE);
    expect(body).toContain("createCaptureTurn(");
    expect(body).toContain(".discard()");
    expect(body).toContain(".finish()");
    expect(body).not.toContain("uri");
  });

  it("the voice module sends segments and keeps the port the voice doctor reads", () => {
    const body = code(VOICE);
    expect(body).toContain("export const ASR_PORT = 8802;");
    expect(body).toContain("transcribeSegmentAt(");
    expect(body).not.toContain("uri");
  });

  it("voice stays __DEV__-only: the pill is rendered under __DEV__ and the lane needs __DEV__", () => {
    const pills = INTAKE.split("__DEV__ && consents?.voice === true ? (").length - 1;
    expect(pills).toBe(2);
    expect(INTAKE).toMatch(/const voiceEligible =\s*__DEV__ &&/);
  });
});
