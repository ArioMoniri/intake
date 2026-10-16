/**
 * The streaming voice session (INT-103): the imperative half that owns
 * connect → publish → sample → reconnect → tear down, over an injected
 * RoomAdapter so the whole lifecycle is unit-testable in node with no native
 * module and no network.
 *
 * INVARIANT 3. This file never opens a file, never imports expo-file-system,
 * and never holds an audio buffer. The microphone is published as a live
 * WebRTC track by the native layer and the frames do not enter JS at all.
 * "Pausing" is `setMicrophoneEnabled(false)` — capture stops at the source —
 * not "record to a buffer and resume later", which would create exactly the
 * 60-second window invariant 3 exists to bound.
 *
 * INVARIANT 9. Nothing here decides what to say, when to say it, or whether
 * something is urgent. The session moves bytes and reports transport facts.
 * The one message it interprets is a RED trigger, and interpreting it means
 * looking up a script id in a catalog that was already on the device — not
 * evaluating a rule.
 *
 * INVARIANT 21. `handleData` is reachable with the entire media plane down.
 * It calls no adapter media method, awaits no track, and touches no audio
 * session; see the RED-with-media-down test.
 */
import { probeVoiceTransport, streamingVoiceSupported } from "./capability";
import type { VoiceSessionEvent, VoiceSessionListener } from "./events";
import { emitTurnQuality, noopMetricSink, type MetricSink } from "./metrics";
import { addSample, closeWindow, openWindow, type QualityWindow } from "./quality";
import type { PrePositionedRed } from "../red/hop";
import { catalogSaysGenericRed, type RedStore } from "../red/store";
import { decodeRedTrigger } from "./red";
import { nextReconnect, tokenNeedsRemint } from "./reconnect";
import type {
  MicrophonePermission,
  RoomAdapter,
  RoomCredentials,
  RuntimeEnvironment,
  SessionFailure,
  SessionPhase,
  TokenSource,
  TurnQuality,
} from "./types";

/** How the host app's lifecycle reaches the session. */
export type AppLifecycle =
  /** Foreground and visible. */
  | "active"
  /** Backgrounded or obscured — the mic must stop. */
  | "background"
  /** An OS audio interruption (an incoming call, Siri, another app). */
  | "interrupted";

export interface VoiceSessionDeps {
  /** Canonical session uuid. The room is `intake-<sessionId>` (INT-090). */
  readonly sessionId: string;
  readonly env: RuntimeEnvironment;
  readonly permission: MicrophonePermission;
  readonly tokens: TokenSource;
  /** Builds the adapter. The real one dynamic-imports LiveKit; tests fake it. */
  readonly createAdapter: () => Promise<RoomAdapter>;
  /**
   * Everything a RED can show, on the device before the session starts (inv. 21):
   * the scripts and the location questions, CD-24's generic entries included.
   */
  readonly red: PrePositionedRed;
  /**
   * Where a RED goes (INT-465): the same store, screen and ask-first logic the
   * HTTP hop feeds, so the two lanes cannot render one RED two ways.
   */
  readonly redStore: Pick<RedStore, "present">;
  readonly sink?: MetricSink;
  readonly now?: () => number;
  readonly sleep?: (ms: number) => Promise<void>;
  /** Must return [0,1). Deterministic in tests. */
  readonly jitter?: () => number;
}

export interface VoiceSession {
  readonly phase: SessionPhase;
  /** Probe → permission → token → connect. Resolves once settled either way. */
  start(): Promise<void>;
  /** Open a quality window for one turn. */
  beginTurn(workId: number): Promise<void>;
  /** Fold one transport reading into the open window. */
  sampleQuality(): Promise<void>;
  /** Close the open window, emit its metrics, and return the figure. */
  endTurn(): Promise<TurnQuality | null>;
  /** Foreground/background/interruption. Pauses and resumes the mic. */
  handleAppState(state: AppLifecycle): Promise<void>;
  /** Leave and release everything. Idempotent. */
  stop(): Promise<void>;
  subscribe(listener: VoiceSessionListener): () => void;
}

export function createVoiceSession(deps: VoiceSessionDeps): VoiceSession {
  const sink = deps.sink ?? noopMetricSink;
  const now = deps.now ?? (() => Date.now());
  const sleep = deps.sleep ?? ((ms: number) => new Promise((r) => setTimeout(r, ms)));
  const jitter = deps.jitter ?? Math.random;
  // INT-465: read once; the catalog is on the device before the session starts.
  const canSayGenericRed = catalogSaysGenericRed(deps.red);

  const listeners = new Set<VoiceSessionListener>();
  let phase: SessionPhase = "idle";
  let adapter: RoomAdapter | null = null;
  let credentials: RoomCredentials | null = null;
  let window: QualityWindow | null = null;
  let unsubscribers: (() => void)[] = [];
  /** Set once stop() runs, so late async work cannot resurrect the session. */
  let closed = false;
  /** True while the mic is intentionally paused (background/interruption). */
  let paused = false;

  const emit = (event: VoiceSessionEvent) => {
    for (const listener of listeners) {
      listener(event);
    }
  };

  const setPhase = (next: SessionPhase) => {
    if (phase === next) {
      return;
    }
    phase = next;
    emit({ type: "phase", phase: next });
  };

  const fail = (reason: SessionFailure) => {
    setPhase("failed");
    emit({ type: "failed", reason });
  };

  /**
   * Inbound data. THE RED PATH — reachable with media entirely torn down
   * (invariant 21). Note there is not one adapter media call in here.
   */
  const handleData = (payload: Uint8Array) => {
    if (closed) {
      return;
    }
    const trigger = decodeRedTrigger(payload);
    if (trigger === null) {
      // Not a RED trigger, or malformed. Refused, never coerced. Other agent
      // message kinds belong to INT-091/092 and are ignored here.
      return;
    }
    // INT-465: the RED store resolves the script, asks first under UNKNOWN, and
    // shows CD-24's generic copy when the script is not on this device — never
    // nothing and never wordless (start() refused a catalog without it).
    // INT-475: the RED names this session, which is its visit's row (INT-197),
    // so the patient's location answer reaches the server for it.
    deps.redStore.present(trigger, deps.red, {
      sessionId: deps.sessionId,
      visitId: deps.sessionId,
    });
    emit({ type: "red", trigger });
  };

  const handleConnectionChange = (state: "connected" | "reconnecting" | "disconnected") => {
    if (closed) {
      return;
    }
    if (state === "connected") {
      setPhase(paused ? "backgrounded" : "connected");
      return;
    }
    if (state === "reconnecting") {
      setPhase("reconnecting");
      return;
    }
    // Dropped. LiveKit's own resume did not carry it, so we run our policy.
    void runReconnect();
  };

  const attach = (next: RoomAdapter) => {
    unsubscribers.push(next.onData(handleData));
    unsubscribers.push(next.onConnectionChange(handleConnectionChange));
  };

  const detach = () => {
    for (const off of unsubscribers) {
      off();
    }
    unsubscribers = [];
  };

  /**
   * `initial` uses the credentials start() just fetched as-is; `resume`
   * re-mints only a stale token; `remint` always does. Keeping the three
   * apart is what stops start() from fetching a token twice when the API
   * hands back one that is already inside the refresh margin.
   */
  const join = async (mode: "initial" | "resume" | "remint"): Promise<void> => {
    const stale =
      credentials === null ||
      mode === "remint" ||
      (mode === "resume" && tokenNeedsRemint(credentials.expiresAtMs, now()));
    if (stale) {
      credentials = await deps.tokens.fetch(deps.sessionId);
    }
    const joining = credentials;
    if (joining === null) {
      // Unreachable: `stale` is true whenever credentials is null, so the
      // fetch above has run. The narrowing is for the type checker.
      throw new Error("no room credentials");
    }
    if (adapter === null) {
      adapter = await deps.createAdapter();
      attach(adapter);
    }
    await adapter.connect(joining);
    // A resumed session must not silently re-open a mic the patient paused.
    await adapter.setMicrophoneEnabled(!paused);
  };

  /**
   * Reconnect with exponential full-jitter backoff, re-minting the room token
   * when it has aged past its 600 s ceiling. The room name is derived from
   * the session id, so a rejoin lands in the SAME room and the server-side
   * Talker keeps its state — the client contributes no dialogue state to the
   * resume (invariant 9).
   */
  const runReconnect = async (): Promise<void> => {
    let attempt = 1;
    for (;;) {
      if (closed) {
        return;
      }
      const decision = nextReconnect({
        attempt,
        tokenExpiresAtMs: credentials?.expiresAtMs ?? 0,
        nowMs: now(),
        jitter,
      });
      if (decision.action === "give_up") {
        fail("reconnect_exhausted");
        return;
      }
      setPhase("reconnecting");
      await sleep(decision.delayMs);
      if (closed) {
        return;
      }
      try {
        await join(decision.action === "remint" ? "remint" : "resume");
        setPhase(paused ? "backgrounded" : "connected");
        return;
      } catch {
        // Transport-level failure. The reason is not logged: a connect error
        // can carry a URL or a token fragment, and neither belongs in a log
        // (invariants 6 and 14). The attempt count is the signal.
        attempt += 1;
      }
    }
  };

  return {
    get phase() {
      return phase;
    },

    async start() {
      if (closed || phase !== "idle") {
        return;
      }
      // 0. INT-465: a session that could not say a generic RED does not begin
      // (CD-24 generic_red_silent_is_never_wordless) — before the microphone,
      // a token or a room.
      if (!canSayGenericRed) {
        fail("red_copy_missing");
        return;
      }
      // 1. Capability, before anything else. Expo Go cannot host the native
      // WebRTC module, and we say so rather than degrading into a fake.
      if (!streamingVoiceSupported(deps.env)) {
        const probe = probeVoiceTransport(deps.env);
        fail(probe.status === "needs_dev_build" ? "needs_dev_build" : "platform_unsupported");
        return;
      }
      // 2. The microphone grant.
      setPhase("requesting_permission");
      let granted: boolean;
      try {
        granted = (await deps.permission.request()).granted;
      } catch {
        granted = false;
      }
      if (granted !== true) {
        fail("permission_denied");
        return;
      }
      if (closed) {
        return;
      }
      // 3. Token, then join.
      setPhase("connecting");
      try {
        credentials = await deps.tokens.fetch(deps.sessionId);
      } catch {
        fail("token_unavailable");
        return;
      }
      if (closed) {
        return;
      }
      try {
        await join("initial");
      } catch {
        fail("connect_failed");
        return;
      }
      if (closed) {
        return;
      }
      setPhase("connected");
    },

    async beginTurn(workId: number) {
      if (closed || adapter === null) {
        window = openWindow(workId, null);
        return;
      }
      let baseline = null;
      try {
        baseline = await adapter.sampleTransport();
      } catch {
        baseline = null; // an unavailable reading is "unknown", not zero
      }
      window = openWindow(workId, baseline);
    },

    async sampleQuality() {
      if (closed || adapter === null || window === null) {
        return;
      }
      try {
        const sample = await adapter.sampleTransport();
        if (sample !== null && window !== null) {
          window = addSample(window, sample);
        }
      } catch {
        // A missed reading lowers `samples`; it never fabricates a value.
      }
    },

    async endTurn() {
      if (window === null) {
        return null;
      }
      // One last reading closes the counter delta as tightly as possible.
      if (!closed && adapter !== null) {
        try {
          const sample = await adapter.sampleTransport();
          if (sample !== null) {
            window = addSample(window, sample);
          }
        } catch {
          // keep whatever the window already holds
        }
      }
      const quality = closeWindow(window);
      window = null;
      emitTurnQuality(sink, deps.sessionId, quality);
      emit({ type: "turn_quality", quality });
      return quality;
    },

    /**
     * Background and interruption both PAUSE: capture stops at the source and
     * the room is kept so the patient can resume mid-sentence rather than
     * restarting the intake. The app declares no iOS background-audio mode,
     * so a long background eventually suspends the process and the drop is
     * handled by the reconnect path on return.
     */
    async handleAppState(state: AppLifecycle) {
      if (closed) {
        return;
      }
      const shouldPause = state !== "active";
      paused = shouldPause;
      if (adapter !== null) {
        try {
          await adapter.setMicrophoneEnabled(!shouldPause);
        } catch {
          // The room may already be gone; the reconnect path owns recovery.
        }
      }
      if (phase === "failed" || phase === "closed") {
        return;
      }
      if (!shouldPause) {
        setPhase(adapter === null ? "idle" : "connected");
        return;
      }
      setPhase(state === "interrupted" ? "interrupted" : "backgrounded");
    },

    async stop() {
      if (closed) {
        return;
      }
      closed = true;
      window = null;
      detach();
      const active = adapter;
      adapter = null;
      credentials = null;
      if (active !== null) {
        try {
          await active.setMicrophoneEnabled(false);
        } catch {
          // leaving anyway
        }
        try {
          await active.disconnect();
        } catch {
          // leaving anyway
        }
      }
      setPhase("closed");
    },

    subscribe(listener: VoiceSessionListener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
}
