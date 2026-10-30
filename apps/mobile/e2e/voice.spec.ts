/**
 * INT-103 acceptance — "mic permission copy per store rules; RTT/jitter/loss
 * attached to turns; reconnect resumes session; background pauses safely".
 *
 * Behavioural coverage of the session lives in
 * src/lib/livekit/session.test.ts (lifecycle, reconnect, quality windows,
 * background/interruption, the RED data path, Expo Go). This file pins the
 * things that are only true of the REPOSITORY: the invariant-3 no-persistence
 * proof over the whole directory, the native/store configuration, the
 * catalogued metric ids, the tr-first copy, and the dialogue seam.
 */
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { en } from "../src/lib/i18n/en";
import { tr } from "../src/lib/i18n/tr";
import { DIALOGUE_WIRING, toDialogueStreamAction } from "../src/lib/livekit/events";
import { EMITTED_METRIC_IDS } from "../src/lib/livekit/metrics";
import { GENERIC_RED_SCRIPT_IDS } from "../src/lib/livekit/red";
import { createVoiceSession } from "../src/lib/livekit/session";
import type { RoomAdapter, TransportSample } from "../src/lib/livekit/types";
import { createRedStore } from "../src/lib/red/store";

const MOBILE = join(__dirname, "..");
const REPO = join(MOBILE, "..", "..");
const LIVEKIT_DIR = join(MOBILE, "src", "lib", "livekit");

const read = (...segments: string[]) => readFileSync(join(...segments), "utf8");

/** Every production source in the streaming voice client. */
function productionSources(): { name: string; source: string }[] {
  return readdirSync(LIVEKIT_DIR)
    .filter((name) => name.endsWith(".ts") && !name.endsWith(".test.ts"))
    .map((name) => ({ name, source: read(LIVEKIT_DIR, name) }));
}

/**
 * Comments in this directory necessarily NAME the things the code must not
 * do — that is what makes the invariants legible to the next reader. The
 * scans below are about code, so they strip comments first; a gate that
 * cannot tell an explanation from a call would push the reasoning out of the
 * source to stay green.
 */
function productionCode(): { name: string; source: string }[] {
  return productionSources().map(({ name, source }) => ({
    name,
    source: source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, ""),
  }));
}

// ---------------------------------------------------------------------------
// Invariant 3 — raw audio is never written anywhere, and the client never
// persists. The dev-tier lane (src/lib/voice.ts) captured to a file and
// deleted it after upload until INT-559 (now e2e/voiceCapture.spec.ts guards
// its file-less capture); this lane has no file at all, and these pins keep
// it that way as the directory grows.
// ---------------------------------------------------------------------------

describe("invariant 3: nothing on the audio path persists", () => {
  it("scans a real corpus (the gate is hollow if it finds nothing)", () => {
    const sources = productionSources();
    expect(sources.length).toBeGreaterThanOrEqual(9);
    expect(sources.map((s) => s.name)).toContain("session.ts");
    expect(sources.map((s) => s.name)).toContain("nativeRoom.ts");
  });

  it("imports no filesystem or storage module", () => {
    const forbidden = [
      "expo-file-system",
      "expo-sqlite",
      "expo-secure-store",
      "@react-native-async-storage",
      "node:fs",
      'from "fs"',
      "react-native-fs",
      "expo-media-library",
    ];
    for (const { name, source } of productionCode()) {
      for (const module of forbidden) {
        expect(source, `${name} must not reach for ${module}`).not.toContain(module);
      }
    }
  });

  it("names no audio artefact and no recorder API", () => {
    // Mirrors the Python audio_retention_guard's literal scan
    // (tests/voice/test_audio_retention_guard.py) on the TypeScript side.
    const audioExtensions = /\.(wav|mp3|ogg|oga|opus|flac|m4a|aac|pcm|amr|aiff|caf|webm)\b/i;
    const recorderApis = [
      "MediaRecorder",
      "useAudioRecorder",
      "prepareToRecordAsync",
      "startRecording",
      "createAudioPlayer",
      "cacheDirectory",
      "documentDirectory",
      "writeAsStringAsync",
      "uploadAsync",
    ];
    for (const { name, source } of productionCode()) {
      expect(source, `${name} names an audio artefact`).not.toMatch(audioExtensions);
      for (const api of recorderApis) {
        expect(source, `${name} reaches for ${api}`).not.toContain(api);
      }
    }
  });

  it("exposes no frame-level or recording method on the adapter surface", () => {
    const types = read(LIVEKIT_DIR, "types.ts");
    for (const method of ["onFrame", "getBuffer", "readPcm", "publishData", "record("]) {
      expect(types).not.toContain(method);
    }
    // canPublishData is pinned false server-side (INT-090), so the client is
    // a data RECEIVER only — onData exists, a publish counterpart must not.
    expect(types).toContain("onData");
  });

  it("drives a whole session without any persistence side effect", async () => {
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
    // Any accidental reach for a storage-shaped global is recorded.
    const globals = globalThis as unknown as Record<string, unknown>;
    const restored = {
      localStorage: globals.localStorage,
      FileReader: globals.FileReader,
    };
    globals.localStorage = trap;
    globals.FileReader = trap;

    try {
      const adapter = fakeAdapter();
      const session = createVoiceSession({
        sessionId: "3f2504e0-4f89-11d3-9a0c-0305e82c3301",
        env: { os: "ios", executionEnvironment: "standalone" },
        permission: { request: async () => ({ granted: true }) },
        tokens: {
          fetch: async () => ({
            url: "wss://sfu.example.invalid",
            token: "a.b.c",
            room: "intake-3f2504e0-4f89-11d3-9a0c-0305e82c3301",
            expiresAtMs: Date.now() + 600_000,
          }),
        },
        createAdapter: async () => adapter,
        // INT-465: a session that cannot say CD-24's generic RED does not start.
        red: {
          scripts: {
            [GENERIC_RED_SCRIPT_IDS.REMOTE]: {
              primary: "CALL_112",
              show112: true,
              actionTr: "Sentetik genel yönerge.",
              doNotsTr: [],
              whyTr: null,
            },
            [GENERIC_RED_SCRIPT_IDS.ON_SITE]: {
              primary: "GO_TO_IN_HOUSE_ACIL",
              show112: false,
              actionTr: "Sentetik yerinde yönerge.",
              doNotsTr: [],
              whyTr: null,
            },
          },
          questions: {
            [GENERIC_RED_SCRIPT_IDS.UNKNOWN]: {
              askTr: "Şu anda hastanede misiniz?",
              onYes: "ON_SITE",
              onNo: "REMOTE",
              onNoAnswer: "REMOTE",
            },
          },
        },
        redStore: createRedStore(),
        sleep: async () => undefined,
        jitter: () => 0.5,
      });

      await session.start();
      await session.beginTurn(1);
      await session.sampleQuality();
      await session.endTurn();
      await session.handleAppState("background");
      await session.handleAppState("active");
      await session.stop();

      expect(touched).toEqual([]);
    } finally {
      globals.localStorage = restored.localStorage;
      globals.FileReader = restored.FileReader;
    }
  });
});

function fakeAdapter(): RoomAdapter {
  const sample: TransportSample = {
    rttMs: 30,
    jitterMs: 4,
    packetsLost: 1,
    packetsTotal: 100,
    relayed: false,
  };
  return {
    connect: async () => undefined,
    disconnect: async () => undefined,
    setMicrophoneEnabled: async () => undefined,
    sampleTransport: async () => sample,
    onData: () => () => undefined,
    onConnectionChange: () => () => undefined,
  };
}

// ---------------------------------------------------------------------------
// Invariant 9 — the client renders; it never decides.
// ---------------------------------------------------------------------------

describe("invariant 9: the tool boundary stays server-side", () => {
  it("names none of the Talker's six tools", () => {
    const tools = [
      "protocol_next",
      "submit_utterance",
      "cancel_work",
      "request_repeat_or_clarify",
      "patient_memory",
      "respond_permission",
    ];
    for (const { name, source } of productionCode()) {
      for (const tool of tools) {
        expect(source, `${name} re-implements the Talker tool ${tool}`).not.toContain(tool);
      }
    }
  });

  it("holds no triage rule, threshold or level of its own", () => {
    for (const { name, source } of productionCode()) {
      for (const token of [
        "YELLOW_REVIEW",
        "KIRMIZI",
        "EK4",
        "evaluate_triage",
        "candidate_flags",
      ]) {
        expect(source, `${name} carries triage logic`).not.toContain(token);
      }
    }
  });

  it("constructs a RED only by decoding an inbound packet", () => {
    // decodeRedTrigger is the single constructor. A `readonly kind:
    // "red_trigger"` in types.ts is the TYPE declaration, not a construction,
    // so the lookbehind lets that through while catching an object literal.
    const construction = /(?<!readonly\s)kind:\s*"red_trigger"/;
    for (const { name, source } of productionCode()) {
      if (name === "red.ts") {
        continue; // the one permitted constructor
      }
      expect(source, `${name} builds a RED trigger locally`).not.toMatch(construction);
    }
  });
});

// ---------------------------------------------------------------------------
// Acceptance: mic permission copy per store rules.
// ---------------------------------------------------------------------------

describe("mic permission copy", () => {
  const keys = [
    "voice.mic.why",
    "voice.mic.cta",
    "voice.mic.settingsHint",
    "voice.transport.needsDevBuild",
    "voice.transport.unsupported",
    "voice.transport.micDenied",
    "voice.session.reconnecting",
    "voice.session.paused",
    "voice.session.interrupted",
  ] as const;

  it("exists in tr and mirrors into en", () => {
    for (const key of keys) {
      expect(tr[key], `tr is missing ${key}`).toBeTruthy();
      expect(en[key], `en is missing ${key}`).toBeTruthy();
    }
  });

  it("uses the siz register and never sen", () => {
    for (const key of keys) {
      expect(tr[key]).not.toMatch(/\bsen\b|\bsana\b|\bsenin\b/iu);
    }
  });

  it("says why before the OS prompt, as the stores require", () => {
    expect(tr["voice.mic.why"]).toMatch(/mikrofon/i);
    expect(tr["voice.mic.why"]).toMatch(/sesli görüşme/i);
  });

  it("never claims a recording is kept — invariant 3 reaches the copy too", () => {
    const plistTr = JSON.parse(read(MOBILE, "src", "locales", "app-tr.json"));
    const plistEn = JSON.parse(read(MOBILE, "src", "locales", "app-en.json"));
    // The iOS purpose string is what App Review reads. It must not promise a
    // recording the product never makes.
    expect(plistTr.NSMicrophoneUsageDescription).toMatch(/saklanmaz/i);
    expect(plistTr.NSMicrophoneUsageDescription).not.toMatch(/kaydetmek/i);
    expect(plistEn.NSMicrophoneUsageDescription).toMatch(/no audio recording is kept/i);
    expect(tr["voice.mic.why"]).toMatch(/saklanmaz/i);
  });
});

// ---------------------------------------------------------------------------
// Acceptance: RTT/jitter/loss attached to turns — invariant 13.
// ---------------------------------------------------------------------------

describe("per-turn network metrics", () => {
  it("emits only ids the metrics catalogue already carries", () => {
    const catalogue = read(REPO, "observability", "metrics_catalog.yaml");
    expect(EMITTED_METRIC_IDS).toEqual(["net.rtt_ms", "net.jitter_ms", "net.packet_loss_ratio"]);
    for (const id of EMITTED_METRIC_IDS) {
      expect(catalogue, `${id} is not catalogued (invariant 13)`).toContain(`id: ${id}`);
      expect(catalogue).toContain(`name: ${id.replace(/\./g, "_")}`);
    }
  });

  it("carries no PHI-risk label in its sample shape (invariant 6)", () => {
    const metrics = read(LIVEKIT_DIR, "metrics.ts");
    for (const label of ["transcript", "utterance", "text", "phone", "name", "free_text"]) {
      expect(metrics).not.toContain(`${label}:`);
    }
  });
});

// ---------------------------------------------------------------------------
// Native / store configuration. No native build is run here — these pin the
// declarations a dev-client build will consume.
// ---------------------------------------------------------------------------

describe("Expo configuration", () => {
  const appJson = JSON.parse(read(MOBILE, "app.json"));
  const plugins = JSON.stringify(appJson.expo.plugins);

  it("registers the LiveKit config plugin and the audio-only plugin", () => {
    expect(plugins).toContain("@livekit/react-native-expo-plugin");
    expect(plugins).toContain("withVoiceAudio");
  });

  it("configures LiveKit for a communication audio session with no video", () => {
    expect(plugins).toContain('"audioType":"communication"');
    expect(plugins).toContain('"enableScreenShareService":false');
    expect(plugins).toContain('"enableMultitaskingCameraAccess":false');
  });

  it("declares the audio permissions the voice path needs", () => {
    const permissions: string[] = appJson.expo.android.permissions;
    expect(permissions).toContain("android.permission.RECORD_AUDIO");
    expect(permissions).toContain("android.permission.MODIFY_AUDIO_SETTINGS");
    expect(permissions).toContain("android.permission.BLUETOOTH_CONNECT");
  });

  it("keeps the no-video guarantee where it actually lives (INT-138)", () => {
    // The CAMERA permission left this app's forbidden list when the records
    // screen gained a still capture (INT-138). The guarantee it stood in for is
    // unchanged, and this file does not restate it by grepping a Python
    // literal — `tests/voice/test_room_tokens.py` DECODES a minted JWT and
    // asserts the grant surface, which is the behaviour rather than the text.
    // What is asserted here is the half that lives in this app's own config.
    expect(plugins).toContain('"enableMultitaskingCameraAccess":false');
    const tokenSuite = read(REPO, "tests", "voice", "test_room_tokens.py");
    expect(tokenSuite).toContain('assert video["canPublishSources"] == ["microphone"]');
    expect(tokenSuite).toContain("def test_video_grant_is_exactly_the_minimal_surface");
  });

  it("the plugin blocks the storage permissions and background audio", () => {
    const plugin = read(MOBILE, "plugins", "withVoiceAudio.js");
    expect(plugin).toContain("android.permission.READ_EXTERNAL_STORAGE");
    expect(plugin).toContain("android.permission.WRITE_EXTERNAL_STORAGE");
    expect(plugin).toContain("FORBIDDEN_PERMISSIONS");
    expect(plugin).toContain("withBlockedPermissions");
    // "background pauses safely" — declaring background audio would let
    // capture continue behind a backgrounded medical app.
    expect(plugin).toContain("UIBackgroundModes");
    expect(plugin).toContain('mode !== "audio"');
  });

  it("pins the LiveKit dependencies at exact versions", () => {
    const pkg = JSON.parse(read(MOBILE, "package.json"));
    for (const name of [
      "@livekit/react-native",
      "@livekit/react-native-webrtc",
      "@livekit/react-native-expo-plugin",
      "livekit-client",
    ]) {
      expect(pkg.dependencies[name], `${name} is not pinned`).toMatch(/^\d+\.\d+\.\d+$/);
    }
  });

  it("never names LiveKit Cloud — the SFU is self-hosted in Türkiye", () => {
    // Assembled, not written out: scripts/ci/assert_no_vendor_calls.sh scans
    // for the literal and would flag this very assertion (the same dodge
    // nav.spec.ts uses for its banned-token list).
    const cloudHost = [".live", "kit", ".cloud"].join("");
    for (const { name, source } of productionSources()) {
      expect(source, `${name} references LiveKit Cloud`).not.toContain(cloudHost);
    }
  });
});

// ---------------------------------------------------------------------------
// The dialogue seam. This issue must not edit stream.ts, DialogueIntake.tsx
// or tts.ts; it exposes an API and documents the one line that joins them.
// ---------------------------------------------------------------------------

describe("dialogue seam", () => {
  it("maps a terminal transport failure onto the reducer's failure action", () => {
    expect(toDialogueStreamAction({ type: "failed", reason: "reconnect_exhausted" })).toEqual({
      type: "failure",
    });
  });

  it("maps nothing else — turn-taking stays server-side (invariant 9)", () => {
    expect(toDialogueStreamAction({ type: "phase", phase: "connected" })).toBeNull();
    expect(
      toDialogueStreamAction({
        type: "turn_quality",
        quality: {
          workId: 1,
          rttMsP50: 1,
          jitterMsP50: 1,
          lossRate: 0,
          relayed: false,
          samples: 1,
        },
      }),
    ).toBeNull();
  });

  it("documents the wiring line the coordinator adds", () => {
    expect(DIALOGUE_WIRING).toContain("toDialogueStreamAction");
    expect(DIALOGUE_WIRING).toContain("dispatch");
  });

  it("leaves the files other issues own untouched", () => {
    // A runtime import of these would couple the lanes; only a type is used.
    const events = read(LIVEKIT_DIR, "events.ts");
    expect(events).toContain("import type { DialogueStreamAction }");
    for (const { name, source } of productionCode()) {
      expect(source, `${name} imports the dialogue runtime`).not.toContain(
        'from "../dialogue/tts"',
      );
      expect(source, `${name} imports the dialogue session`).not.toContain("useDialogueSession");
    }
  });
});
