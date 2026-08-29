/**
 * Session lifecycle, reconnect, quality sampling, background/interruption,
 * the RED data path and the Expo Go degradation (INT-103).
 *
 * Everything runs in node against injected fakes — no native module, no
 * network, no timers. That is the point of the RoomAdapter seam.
 */
import { describe, expect, it, vi } from "vitest";

import { createVoiceSession, type AppLifecycle, type VoiceSessionDeps } from "./session";
import type { VoiceSessionEvent } from "./events";
import type { RedScriptCatalog } from "./red";
import type { RoomAdapter, RoomCredentials, RuntimeEnvironment, TransportSample } from "./types";

const SESSION_ID = "3f2504e0-4f89-11d3-9a0c-0305e82c3301";

const DEV_BUILD: RuntimeEnvironment = { os: "ios", executionEnvironment: "standalone" };
const EXPO_GO: RuntimeEnvironment = { os: "ios", executionEnvironment: "storeClient" };

function credentials(expiresAtMs: number): RoomCredentials {
  return {
    url: "wss://sfu.example.invalid",
    token: "header.payload.signature",
    room: `intake-${SESSION_ID}`,
    expiresAtMs,
  };
}

function sample(over: Partial<TransportSample> = {}): TransportSample {
  return {
    rttMs: 40,
    jitterMs: 5,
    packetsLost: 0,
    packetsTotal: 100,
    relayed: false,
    ...over,
  };
}

/**
 * A controllable room. `mediaDown` makes every MEDIA call throw while leaving
 * the data channel working — the shape of a torn-down media plane.
 */
class FakeAdapter implements RoomAdapter {
  connects = 0;
  micStates: boolean[] = [];
  mediaDown = false;
  failConnectTimes = 0;
  samples: (TransportSample | null)[] = [];
  private dataListeners: ((p: Uint8Array) => void)[] = [];
  private stateListeners: ((s: "connected" | "reconnecting" | "disconnected") => void)[] = [];

  async connect(): Promise<void> {
    if (this.failConnectTimes > 0) {
      this.failConnectTimes -= 1;
      throw new Error("connect refused");
    }
    this.connects += 1;
  }

  async disconnect(): Promise<void> {
    this.mediaDown = true;
  }

  async setMicrophoneEnabled(enabled: boolean): Promise<void> {
    if (this.mediaDown) {
      throw new Error("no media plane");
    }
    this.micStates.push(enabled);
  }

  async sampleTransport(): Promise<TransportSample | null> {
    if (this.mediaDown) {
      throw new Error("no media plane");
    }
    return this.samples.shift() ?? null;
  }

  onData(listener: (p: Uint8Array) => void): () => void {
    this.dataListeners.push(listener);
    return () => {
      this.dataListeners = this.dataListeners.filter((l) => l !== listener);
    };
  }

  onConnectionChange(
    listener: (s: "connected" | "reconnecting" | "disconnected") => void,
  ): () => void {
    this.stateListeners.push(listener);
    return () => {
      this.stateListeners = this.stateListeners.filter((l) => l !== listener);
    };
  }

  /** Deliver one data-channel packet. Never touches media. */
  pushData(message: unknown): void {
    const bytes = new TextEncoder().encode(JSON.stringify(message));
    for (const listener of [...this.dataListeners]) {
      listener(bytes);
    }
  }

  pushState(state: "connected" | "reconnecting" | "disconnected"): void {
    for (const listener of [...this.stateListeners]) {
      listener(state);
    }
  }
}

const RED_SCRIPTS: RedScriptCatalog = {
  "life_threat.chest_pain.remote": {
    primary: "CALL_112",
    show112: true,
    actionTr: "Hemen 112'yi arayın.",
    doNotsTr: ["Araç kullanmayın."],
    whyTr: "Belirtileriniz acil değerlendirme gerektirebilir.",
  },
  "life_threat.chest_pain.on_site": {
    primary: "GO_TO_IN_HOUSE_ACIL",
    // The pack authorises 112 here; ON_SITE must still suppress it.
    show112: true,
    actionTr: "En yakın görevliye hemen haber verin.",
    doNotsTr: [],
    whyTr: null,
  },
};

interface Harness {
  readonly deps: VoiceSessionDeps;
  readonly adapter: FakeAdapter;
  readonly events: VoiceSessionEvent[];
  readonly tokenFetches: () => number;
}

function harness(over: Partial<VoiceSessionDeps> = {}, adapter = new FakeAdapter()): Harness {
  const events: VoiceSessionEvent[] = [];
  let fetches = 0;
  let clock = 1_000_000;
  const deps: VoiceSessionDeps = {
    sessionId: SESSION_ID,
    env: DEV_BUILD,
    permission: { request: async () => ({ granted: true }) },
    tokens: {
      fetch: async () => {
        fetches += 1;
        return credentials(clock + 600_000);
      },
    },
    createAdapter: async () => adapter,
    redScripts: RED_SCRIPTS,
    now: () => clock,
    sleep: async () => undefined,
    jitter: () => 0.5,
    ...over,
  };
  return { deps, adapter, events, tokenFetches: () => fetches };
}

function collect(session: { subscribe: (l: (e: VoiceSessionEvent) => void) => void }) {
  const events: VoiceSessionEvent[] = [];
  session.subscribe((e) => events.push(e));
  return events;
}

describe("session lifecycle", () => {
  it("probes, asks permission, fetches a token and connects", async () => {
    const { deps, adapter, tokenFetches } = harness();
    const session = createVoiceSession(deps);
    const events = collect(session);

    await session.start();

    expect(session.phase).toBe("connected");
    expect(adapter.connects).toBe(1);
    expect(tokenFetches()).toBe(1);
    // The mic is enabled exactly once, by the join.
    expect(adapter.micStates).toEqual([true]);
    expect(events.map((e) => (e.type === "phase" ? e.phase : e.type))).toEqual([
      "requesting_permission",
      "connecting",
      "connected",
    ]);
  });

  it("refuses to start when the microphone is denied, and never connects", async () => {
    const { deps, adapter } = harness({
      permission: { request: async () => ({ granted: false }) },
    });
    const session = createVoiceSession(deps);
    const events = collect(session);

    await session.start();

    expect(session.phase).toBe("failed");
    expect(adapter.connects).toBe(0);
    expect(events).toContainEqual({ type: "failed", reason: "permission_denied" });
  });

  it("reports token_unavailable rather than inventing a token", async () => {
    const { deps, adapter } = harness({
      tokens: {
        fetch: async () => {
          throw new Error("no route");
        },
      },
    });
    const session = createVoiceSession(deps);
    const events = collect(session);

    await session.start();

    expect(events).toContainEqual({ type: "failed", reason: "token_unavailable" });
    expect(adapter.connects).toBe(0);
  });

  it("stop() mutes, disconnects and is idempotent", async () => {
    const { deps, adapter } = harness();
    const session = createVoiceSession(deps);
    await session.start();

    await session.stop();
    await session.stop();

    expect(session.phase).toBe("closed");
    expect(adapter.mediaDown).toBe(true);
    expect(adapter.micStates).toEqual([true, false]);
  });
});

describe("Expo Go degradation", () => {
  it("refuses honestly with needs_dev_build and never asks for the mic", async () => {
    const permission = { request: vi.fn(async () => ({ granted: true })) };
    const { deps, adapter } = harness({ env: EXPO_GO, permission });
    const session = createVoiceSession(deps);
    const events = collect(session);

    await session.start();

    expect(session.phase).toBe("failed");
    expect(events).toContainEqual({ type: "failed", reason: "needs_dev_build" });
    // The honest refusal comes BEFORE any permission prompt or connection —
    // no silent fallback to a fake session (invariant 17).
    expect(permission.request).not.toHaveBeenCalled();
    expect(adapter.connects).toBe(0);
  });

  it("refuses on an unsupported platform", async () => {
    const { deps } = harness({ env: { os: "web", executionEnvironment: "bare" } });
    const session = createVoiceSession(deps);
    const events = collect(session);

    await session.start();

    expect(events).toContainEqual({ type: "failed", reason: "platform_unsupported" });
  });
});

describe("per-turn network quality", () => {
  it("attaches RTT, jitter and a windowed loss RATE to the turn", async () => {
    const adapter = new FakeAdapter();
    // baseline, mid, close: 20 of 200 packets lost within THIS window.
    adapter.samples = [
      sample({ packetsLost: 5, packetsTotal: 1000, rttMs: 30, jitterMs: 4 }),
      sample({ packetsLost: 15, packetsTotal: 1100, rttMs: 50, jitterMs: 8 }),
      sample({ packetsLost: 25, packetsTotal: 1200, rttMs: 70, jitterMs: 12 }),
    ];
    const { deps } = harness({}, adapter);
    const session = createVoiceSession(deps);
    await session.start();

    await session.beginTurn(7);
    await session.sampleQuality();
    const quality = await session.endTurn();

    expect(quality).not.toBeNull();
    expect(quality?.workId).toBe(7);
    // Session total would be 25/1200; the turn's own window is 20/200.
    expect(quality?.lossRate).toBeCloseTo(0.1, 6);
    expect(quality?.rttMsP50).toBe(50);
    expect(quality?.jitterMsP50).toBe(8);
    expect(quality?.samples).toBe(2);
  });

  it("emits only catalogued metric ids, carrying ids and never text", async () => {
    const adapter = new FakeAdapter();
    adapter.samples = [sample(), sample({ packetsTotal: 200, packetsLost: 2 })];
    const emitted: { metricId: string; value: number; sessionId: string; workId: number }[] = [];
    const { deps } = harness({ sink: { emit: (s) => emitted.push(s) } }, adapter);
    const session = createVoiceSession(deps);
    await session.start();

    await session.beginTurn(3);
    await session.endTurn();

    expect(emitted.map((s) => s.metricId).sort()).toEqual([
      "net.jitter_ms",
      "net.packet_loss_ratio",
      "net.rtt_ms",
    ]);
    for (const item of emitted) {
      expect(item.sessionId).toBe(SESSION_ID);
      expect(item.workId).toBe(3);
      expect(Object.keys(item).sort()).toEqual(["metricId", "sessionId", "value", "workId"]);
    }
  });

  it("emits nothing for a turn it never measured, rather than a confident zero", async () => {
    const adapter = new FakeAdapter();
    adapter.samples = []; // sampleTransport resolves null throughout
    const emitted: unknown[] = [];
    const { deps } = harness({ sink: { emit: (s) => emitted.push(s) } }, adapter);
    const session = createVoiceSession(deps);
    await session.start();

    await session.beginTurn(1);
    const quality = await session.endTurn();

    expect(quality?.samples).toBe(0);
    expect(emitted).toEqual([]);
  });
});

describe("reconnect", () => {
  it("resumes into the same room and re-uses a still-valid token", async () => {
    const adapter = new FakeAdapter();
    const { deps, tokenFetches } = harness({}, adapter);
    const session = createVoiceSession(deps);
    await session.start();
    expect(tokenFetches()).toBe(1);

    adapter.pushState("disconnected");
    await vi.waitFor(() => expect(session.phase).toBe("connected"));

    expect(adapter.connects).toBe(2);
    // Token was fresh (600 s ahead), so no re-mint was needed.
    expect(tokenFetches()).toBe(1);
  });

  it("re-mints an expiring token before rejoining", async () => {
    const adapter = new FakeAdapter();
    let clock = 1_000_000;
    let fetches = 0;
    const session = createVoiceSession({
      ...harness({}, adapter).deps,
      now: () => clock,
      tokens: {
        fetch: async () => {
          fetches += 1;
          // A token already inside the 30 s refresh margin.
          return credentials(clock + 5_000);
        },
      },
    });
    await session.start();
    expect(fetches).toBe(1);

    clock += 1_000;
    adapter.pushState("disconnected");
    await vi.waitFor(() => expect(session.phase).toBe("connected"));

    expect(fetches).toBe(2);
    expect(adapter.connects).toBe(2);
  });

  it("gives up honestly after the attempt ceiling instead of looping forever", async () => {
    const adapter = new FakeAdapter();
    adapter.failConnectTimes = 99;
    const { deps } = harness({}, adapter);
    const session = createVoiceSession(deps);
    await session.start();
    const events = collect(session);

    adapter.pushState("disconnected");
    await vi.waitFor(() => expect(session.phase).toBe("failed"));

    expect(events).toContainEqual({ type: "failed", reason: "reconnect_exhausted" });
  });

  it("does not reconnect after stop()", async () => {
    const adapter = new FakeAdapter();
    const { deps } = harness({}, adapter);
    const session = createVoiceSession(deps);
    await session.start();
    await session.stop();
    const before = adapter.connects;

    adapter.pushState("disconnected");
    await Promise.resolve();

    expect(adapter.connects).toBe(before);
    expect(session.phase).toBe("closed");
  });
});

describe("background and interruption", () => {
  const cases: readonly [AppLifecycle, string][] = [
    ["background", "backgrounded"],
    ["interrupted", "interrupted"],
  ];

  for (const [state, phase] of cases) {
    it(`${state} pauses the microphone at the source`, async () => {
      const { deps, adapter } = harness();
      const session = createVoiceSession(deps);
      await session.start();

      await session.handleAppState(state);

      expect(session.phase).toBe(phase);
      expect(adapter.micStates).toEqual([true, false]);
    });
  }

  it("returning to the foreground resumes capture", async () => {
    const { deps, adapter } = harness();
    const session = createVoiceSession(deps);
    await session.start();

    await session.handleAppState("background");
    await session.handleAppState("active");

    expect(session.phase).toBe("connected");
    expect(adapter.micStates).toEqual([true, false, true]);
  });

  it("a reconnect while backgrounded does not silently re-open the mic", async () => {
    const adapter = new FakeAdapter();
    const { deps } = harness({}, adapter);
    const session = createVoiceSession(deps);
    await session.start();
    await session.handleAppState("background");

    adapter.pushState("disconnected");
    await vi.waitFor(() => expect(session.phase).toBe("backgrounded"));

    expect(adapter.micStates).toEqual([true, false, false]);
  });
});

describe("RED over the data channel (invariant 21)", () => {
  it("renders with the media plane torn down", async () => {
    const adapter = new FakeAdapter();
    const { deps } = harness({}, adapter);
    const session = createVoiceSession(deps);
    await session.start();
    const events = collect(session);

    // Tear the media plane down: every media call now throws.
    await adapter.disconnect();
    expect(adapter.mediaDown).toBe(true);
    await expect(adapter.sampleTransport()).rejects.toThrow();

    adapter.pushData({
      kind: "red_trigger",
      ruleId: "life_threat.chest_pain",
      register: "ALERT",
      location: "REMOTE",
      scriptId: "life_threat.chest_pain.remote",
    });

    const red = events.find((e) => e.type === "red");
    expect(red).toBeDefined();
    if (red?.type !== "red") {
      throw new Error("expected a red event");
    }
    expect(red.presentation.register).toBe("ALERT");
    expect(red.presentation.location).toBe("REMOTE");
    expect(red.presentation.script.actionTr).toBe("Hemen 112'yi arayın.");
    expect(red.presentation.show112).toBe(true);
  });

  it("suppresses the 112 affordance under ON_SITE even when the pack allows it", async () => {
    const adapter = new FakeAdapter();
    const { deps } = harness({}, adapter);
    const session = createVoiceSession(deps);
    await session.start();
    const events = collect(session);

    adapter.pushData({
      kind: "red_trigger",
      ruleId: "life_threat.chest_pain",
      register: "ALERT",
      location: "ON_SITE",
      scriptId: "life_threat.chest_pain.on_site",
    });

    const red = events.find((e) => e.type === "red");
    if (red?.type !== "red") {
      throw new Error("expected a red event");
    }
    expect(red.presentation.show112).toBe(false);
  });

  it("says so honestly when the script is not pre-positioned", async () => {
    const adapter = new FakeAdapter();
    const { deps } = harness({}, adapter);
    const session = createVoiceSession(deps);
    await session.start();
    const events = collect(session);

    adapter.pushData({
      kind: "red_trigger",
      ruleId: "life_threat.unknown",
      register: "CALM",
      location: "REMOTE",
      scriptId: "life_threat.not.on.this.device",
    });

    expect(events).toContainEqual({ type: "red_unrenderable", ruleId: "life_threat.unknown" });
    expect(events.some((e) => e.type === "red")).toBe(false);
  });

  it("ignores non-RED and malformed traffic without emitting anything", async () => {
    const adapter = new FakeAdapter();
    const { deps } = harness({}, adapter);
    const session = createVoiceSession(deps);
    await session.start();
    const events = collect(session);

    adapter.pushData({ kind: "transcript", text: "karnım ağrıyor" });
    adapter.pushData({ kind: "red_trigger", ruleId: "x", scriptId: "y" }); // no axes
    adapter.pushData({
      kind: "red_trigger",
      ruleId: "life_threat.chest_pain",
      register: "LOUD", // not a register
      location: "REMOTE",
      scriptId: "life_threat.chest_pain.remote",
    });

    expect(events).toEqual([]);
  });
});
