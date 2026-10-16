/**
 * Typed boundary for the production voice transport (INT-103): the mobile
 * half of the LiveKit streaming session that supersedes the dev-tier
 * record→upload→transcribe loop in lib/voice.ts.
 *
 * INVARIANT 3 IS THE LOAD-BEARING RULE OF THIS WHOLE DIRECTORY. The patient's
 * microphone is published as a live WebRTC track and nothing else. No module
 * under lib/livekit/ may:
 *   - open a file handle, name an audio file, or touch expo-file-system;
 *   - hold a decoded PCM/Opus buffer in JS at all (frames never cross into
 *     the JS bridge — the native peer connection owns them end to end);
 *   - put transcript text, audio bytes or any patient utterance into a log,
 *     a metric attribute or an error message (invariant 6).
 * `session.no-persistence.test.ts` proves the first and third of these by
 * static scan over this directory plus a runtime spy on the injected
 * filesystem/logging seams; the second is structural — the adapter surface
 * below exposes no frame-level API to reach for.
 *
 * INVARIANT 9: every rule about what may be said, when it may be said and
 * which tools exist lives SERVER-side in the Talker. This client owns
 * transport and rendering only. It never decides urgency, never schedules a
 * speech window, and never re-implements the six-tool boundary. Anything the
 * patient sees arrives as an instruction from the agent.
 *
 * Server contract this file is written against (INT-090,
 * packages/intake_platform/room_tokens.py + infra/livekit/livekit-dev.yaml):
 *   - one room per intake session, named `intake-<session uuid>`;
 *   - HS256 token, TTL <= 600 s, grants exactly roomJoin + canSubscribe +
 *     canPublish restricted to `canPublishSources: ["microphone"]`;
 *   - `canPublishData` is pinned to an explicit FALSE, so this client is a
 *     data-channel RECEIVER only — see RedTrigger below;
 *   - the room is audio-only (`audio/opus` is the sole enabled codec) and
 *     ephemeral; no egress, ingress or recorder exists to write audio to.
 */
import type { RedLocation, RedRegister } from "./red";

/**
 * The honest capability ladder, mirroring lib/health's (INT-208). LiveKit's
 * native module cannot exist in Expo Go, so `needs_dev_build` is the truth we
 * tell there — never a silent fake, never a dead button.
 */
export type VoiceTransportStatus =
  "ok" | "needs_dev_build" | "platform_unsupported" | "permission_denied";

export interface VoiceTransportAvailability {
  readonly status: VoiceTransportStatus;
  /**
   * Resource key for the honest explanation the UI renders for this status.
   * Never a raw sentence — tr is the source of truth (invariant 5).
   */
  readonly messageKey: string;
}

/** Which transport serves this runtime. */
export type VoiceTransportKind = "livekit" | "expo_go_stub" | "unsupported";

/** The two runtime facts the capability decision needs; wiring injects them. */
export interface RuntimeEnvironment {
  /** Platform.OS at the call site. */
  readonly os: string;
  /** Constants.executionEnvironment: "storeClient" is Expo Go. */
  readonly executionEnvironment: string;
}

// --- token + connection ------------------------------------------------------

/**
 * What the API hands back for one session room. The client never mints a
 * token and never sees the signing secret: `mint_room_token` is server-side
 * (INT-090) and the grants above are not negotiable from here.
 */
export interface RoomCredentials {
  /** `wss://…` signalling URL of the self-hosted SFU (files/03 §4.4). */
  readonly url: string;
  /** HS256 JWT, <= 600 s. Treated as opaque — never decoded, never logged. */
  readonly token: string;
  /** `intake-<session uuid>`; derived from ids only, so it carries no PHI. */
  readonly room: string;
  /** Epoch millis at which the token stops being usable; drives renewal. */
  readonly expiresAtMs: number;
}

/**
 * Connection lifecycle as this client models it. `reconnecting` is LiveKit's
 * own resume attempt; `resuming` is ours, after the token had to be re-minted.
 */
export type SessionPhase =
  | "idle"
  | "requesting_permission"
  | "connecting"
  | "connected"
  | "reconnecting"
  | "backgrounded"
  | "interrupted"
  | "closed"
  | "failed";

/** Why a session ended, for the caller's fallback decision. Ids/codes only. */
export type SessionFailure =
  | "permission_denied"
  | "needs_dev_build"
  | "platform_unsupported"
  | "token_unavailable"
  | "connect_failed"
  | "reconnect_exhausted"
  /** INT-465: the catalog cannot say CD-24's generic RED, so the session does not begin. */
  | "red_copy_missing";

// --- per-turn network quality (the acceptance's RTT/jitter/loss) -------------

/**
 * One transport stats reading. Every field is a transport measurement — there
 * is deliberately no room here for anything derived from audio CONTENT.
 */
export interface TransportSample {
  /** Round-trip time in milliseconds, from the selected ICE candidate pair. */
  readonly rttMs: number;
  /** Jitter in milliseconds on the inbound audio stream. */
  readonly jitterMs: number;
  /** Cumulative packets lost on the session so far. */
  readonly packetsLost: number;
  /** Cumulative packets sent+received on the session so far. */
  readonly packetsTotal: number;
  /**
   * True when media is running over a TCP/TLS relay. files/03 §4.4b treats
   * relay selection as degradation trigger T4, not a success.
   */
  readonly relayed: boolean;
}

/**
 * The quality figure attached to one turn. Loss is a RATE over the turn's own
 * window (cumulative counters differenced), not a session total — a turn late
 * in a long session must not inherit earlier loss.
 */
export interface TurnQuality {
  /** The turn this measures. An id, never the utterance text (invariant 6). */
  readonly workId: number;
  readonly rttMsP50: number;
  readonly jitterMsP50: number;
  /** Fraction in [0,1] over this turn's window. */
  readonly lossRate: number;
  /** True if ANY sample in the window came over a TCP/TLS relay. */
  readonly relayed: boolean;
  /** How many samples backed this figure; 0 means "no reading", not "perfect". */
  readonly samples: number;
}

// --- data channel: the RED path (invariant 21) -------------------------------

/**
 * A RED trigger as it arrives over the LiveKit DATA channel.
 *
 * Invariant 21: the RED script is PRE-POSITIONED on the device and triggered
 * over the data channel, so the RED path touches no media transport. This
 * message therefore carries identifiers and axes only — never script text.
 * The device resolves `scriptId` against the compiled pack it already holds,
 * which is what lets a RED render correctly with the microphone track, the
 * audio session and the entire media plane already torn down.
 *
 * Invariant 9: only a rules-engine RED may preempt. The client does not
 * decide that — it renders this message. There is no client-side path that
 * can construct a RedTrigger from anything other than an inbound data packet.
 */
export interface RedTrigger {
  readonly kind: "red_trigger";
  /** Rules-engine rule id (packages/protocols/triage). */
  readonly ruleId: string;
  /** How it is told. No default is permitted (invariant 21). */
  readonly register: RedRegister;
  /** What it tells the patient to do. No default is permitted. */
  readonly location: RedLocation;
  /** Addresses the pre-positioned script in the on-device pack. */
  readonly scriptId: string;
}

// --- the adapter surface -----------------------------------------------------

/**
 * The narrow slice of LiveKit this client needs, behind an interface so the
 * orchestrator stays unit-testable in node with a fake and so no LiveKit
 * import exists on any code path Expo Go can reach.
 *
 * Note what is ABSENT and must stay absent: no frame callback, no PCM
 * accessor, no recorder, no `startRecording`, no track-to-file API. Invariant
 * 3 is enforced by the shape of this interface, not by a rule someone must
 * remember.
 */
export interface RoomAdapter {
  /** Join the room and publish the microphone. Resolves when connected. */
  connect(credentials: RoomCredentials): Promise<void>;
  /** Stop publishing and leave. Idempotent; safe to call from teardown. */
  disconnect(): Promise<void>;
  /** Mute/unmute the published mic track without leaving the room. */
  setMicrophoneEnabled(enabled: boolean): Promise<void>;
  /** One transport reading, or null when no pair is selected yet. */
  sampleTransport(): Promise<TransportSample | null>;
  /** Inbound data packets. Returns an unsubscribe function. */
  onData(listener: (payload: Uint8Array) => void): () => void;
  /** Connection-state transitions the SFU reports. Returns unsubscribe. */
  onConnectionChange(listener: (state: AdapterConnectionState) => void): () => void;
}

export type AdapterConnectionState = "connected" | "reconnecting" | "disconnected";

/** How the app asks for the microphone. Injected so tests need no native module. */
export interface MicrophonePermission {
  request(): Promise<{ readonly granted: boolean }>;
}

/** How the client obtains a room token. The API mints it; we only fetch. */
export interface TokenSource {
  fetch(sessionId: string): Promise<RoomCredentials>;
}
