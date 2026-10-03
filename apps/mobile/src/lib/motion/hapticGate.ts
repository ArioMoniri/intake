/**
 * The live half of the haptic policy (INT-340, MOTION-11; §3 S-3, §2.1 #10).
 *
 * Pure and dependency-injected: the device arrives as a `HapticEngine`, so the
 * gate is node-testable and nothing here reaches react-native or the native
 * module. ./appHaptics.ts builds the app's one gate over the lazy adapter.
 *
 * What the gate adds to `hapticFor`:
 *
 * - **Read at fire time.** The voice session and the microphone are never
 *   passed in by the caller, where a value read at render could be stale.
 *   Their owners register probes, and the gate calls them when the handler
 *   asks and again just before the native call, after the adapter has loaded.
 *   Both reads must be clear. A probe that throws counts as hot.
 * - **RED.** `presentRed` holds every haptic while ALERT, CALM or SILENT is on
 *   screen. DEFERRED_CLINICIAN is invisible to the patient, so it changes
 *   nothing here either (ADR-033 §5). An unknown register fails closed.
 * - **Sticky suppression.** A SILENT RED or a third party sets a flag that
 *   nothing clears: the gate has no method that could. The session is the
 *   gate's life, which in the app is the process, the same life as the
 *   companion declaration it listens to (lib/profile/store.ts). Only a new
 *   session starts clean.
 * - **One haptic per commit, and one per action.** The first request a commit
 *   lets through holds the rest of that commit; a request whose action id was
 *   already asked for is a duplicate, whether it played or not, so a
 *   confirmation handled twice is felt once and a late one is never felt.
 *
 * The request is never awaited before rendering, and a failure to load or to
 * play is swallowed: a haptic is never the only feedback, and it can never
 * break the handler that asked for it.
 */
import {
  hapticAllowed,
  hapticFor,
  type GateRedRegister,
  type HapticCall,
  type HapticEvent,
  type HapticGateContext,
  type HapticPlatform,
  type HapticSurface,
} from "./haptics";

/** What a handler supplies. The live state is deliberately not part of it. */
export interface HapticRequest {
  readonly surface: HapticSurface;
  /** The action this acknowledges (see `HapticGate.action`); one haptic per action. */
  readonly actionId?: string;
  /** `select`: the value differs from the one before. */
  readonly valueChanged?: boolean;
  /** `success`: the server's answer, never a literal. */
  readonly serverConfirmed?: boolean;
}

/** A live owner of the audio session or the microphone, read at fire time. */
export interface HapticProbe {
  voiceSessionActive?(): boolean;
  micHot?(): boolean;
}

/** The device half: the platform it runs on, and one call played. */
export interface HapticEngine {
  readonly platform: HapticPlatform;
  play(call: HapticCall): Promise<void>;
}

export interface HapticGateDeps {
  /** Loaded on the first request that passes the gate, never before. */
  loadEngine(): Promise<HapticEngine>;
  /** Runs `release` once the current commit is over. Default: the next microtask. */
  afterCommit?(release: () => void): void;
}

export interface HapticGate {
  /** Ask for `event`. Resolves to what was played, or `null`. Never rejects. */
  request(event: HapticEvent, request: HapticRequest): Promise<HapticCall | null>;
  /** A fresh action id, minted by the press whose outcome a later `success` confirms. */
  action(): string;
  /** Register a live probe; the returned function releases it (on unmount). */
  register(probe: HapticProbe): () => void;
  /** A RED is on screen until the returned function is called. */
  presentRed(register: GateRedRegister): () => void;
  /** A third party (or a SILENT RED) occurred: no haptic for the rest of the session. */
  markSilentOrThirdParty(): void;
  silentOrThirdPartyThisSession(): boolean;
}

/** How many action ids are remembered; far more than any screen asks for at once. */
const REMEMBERED_ACTIONS = 64;

function nextMicrotask(release: () => void): void {
  void Promise.resolve().then(release);
}

export function createHapticGate(deps: HapticGateDeps): HapticGate {
  const afterCommit = deps.afterCommit ?? nextMicrotask;
  /** One entry per registration, so the same probe twice counts twice. */
  const probes = new Set<{ readonly probe: HapticProbe }>();
  const reds = new Set<object>();
  const asked: string[] = [];
  let sticky = false;
  let heldForCommit = false;
  let minted = 0;

  /** True when any registered probe says so, or cannot say. */
  function anyLive(read: (probe: HapticProbe) => (() => boolean) | undefined): boolean {
    for (const { probe } of probes) {
      const answer = read(probe);
      if (answer === undefined) {
        continue;
      }
      try {
        if (answer.call(probe) !== false) {
          return true;
        }
      } catch {
        return true;
      }
    }
    return false;
  }

  /** The live context, read now. Only the request's own fields are copied. */
  function contextNow(request: HapticRequest): HapticGateContext {
    return {
      voiceSessionActive: anyLive((p) => p.voiceSessionActive),
      micHot: anyLive((p) => p.micHot),
      redPresented: reds.size > 0,
      silentOrThirdPartyThisSession: sticky,
      surface: request.surface,
      valueChanged: request.valueChanged,
      serverConfirmed: request.serverConfirmed,
    };
  }

  function mint(): string {
    minted += 1;
    return `haptic-action-${minted}`;
  }

  /** Records `id`; false when it was asked for already. */
  function firstAsk(id: string): boolean {
    if (asked.includes(id)) {
      return false;
    }
    asked.push(id);
    if (asked.length > REMEMBERED_ACTIONS) {
      asked.shift();
    }
    return true;
  }

  async function request(event: HapticEvent, req: HapticRequest): Promise<HapticCall | null> {
    // Everything up to the first await runs in the handler's own commit.
    if (!firstAsk(req.actionId ?? mint())) {
      return null;
    }
    if (!hapticAllowed(event, contextNow(req)) || heldForCommit) {
      return null;
    }
    heldForCommit = true;
    afterCommit(() => {
      heldForCommit = false;
    });
    let engine: HapticEngine;
    try {
      engine = await deps.loadEngine();
    } catch {
      return null;
    }
    // Read again at the moment of the native call: the microphone may have
    // opened while the adapter loaded.
    const call = hapticFor(event, { ...contextNow(req), platform: engine.platform });
    if (call === null) {
      return null;
    }
    try {
      await engine.play(call);
    } catch {
      return null;
    }
    return call;
  }

  return {
    request,
    action: mint,
    register(probe) {
      const entry = { probe };
      probes.add(entry);
      return () => {
        probes.delete(entry);
      };
    },
    presentRed(register) {
      if (register === "DEFERRED_CLINICIAN") {
        return () => undefined;
      }
      if (register !== "ALERT" && register !== "CALM") {
        // SILENT, and fail-closed for anything the schema does not define.
        sticky = true;
      }
      const token = {};
      reds.add(token);
      return () => {
        reds.delete(token);
      };
    },
    markSilentOrThirdParty() {
      sticky = true;
    },
    silentOrThirdPartyThisSession: () => sticky,
  };
}
