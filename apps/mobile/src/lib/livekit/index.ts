/**
 * Streaming voice wiring (INT-103). The ONLY file under lib/livekit that
 * reads the real runtime — Platform, Expo Constants, expo-audio, the authed
 * fetch. Everything it composes is pure and node-tested, so this switch stays
 * mechanical and untested by design (the lib/health precedent, INT-208).
 *
 * The public surface of the streaming voice client is re-exported here; no
 * caller should reach into the individual modules.
 */
import Constants from "expo-constants";
import { AudioModule } from "expo-audio";
import { Platform } from "react-native";

import { authedFetch } from "../auth/api";
import { probeVoiceTransport } from "./capability";
import { createNativeRoomAdapter } from "./nativeRoom";
import { redStore } from "../red/store";
import { createVoiceSession, type VoiceSession, type VoiceSessionDeps } from "./session";
import { createTokenSource } from "./token";
import type { MicrophonePermission, RuntimeEnvironment, VoiceTransportAvailability } from "./types";

/** The live runtime facts the pure capability probe needs. */
export function currentRuntime(): RuntimeEnvironment {
  return {
    os: Platform.OS,
    executionEnvironment: Constants.executionEnvironment ?? "bare",
  };
}

/**
 * Can this build stream at all? Call before offering the voice affordance so
 * Expo Go shows the honest "needs the full build" message rather than a
 * control that cannot work.
 */
export function voiceTransportAvailability(): VoiceTransportAvailability {
  return probeVoiceTransport(currentRuntime());
}

/**
 * The microphone grant, through expo-audio — the same module the dev-tier
 * dialogue already uses, so the app asks once with one prompt.
 */
export const expoMicrophonePermission: MicrophonePermission = {
  request: async () => {
    const permission = await AudioModule.requestRecordingPermissionsAsync();
    return { granted: permission.granted };
  },
};

/**
 * Build a session for one visit against the real runtime.
 *
 * `red` is REQUIRED and is the pre-positioned RED catalog the app already
 * holds: invariant 21 puts the RED script on the device before the session
 * starts, so it renders with the media plane gone. There is no default and no
 * lazy fetch — a session that could not render a RED must not begin. A RED goes
 * to the app's one RED store (INT-465), where RedLayer renders it.
 */
export function createLiveVoiceSession(
  options: Pick<VoiceSessionDeps, "sessionId" | "red" | "sink">,
): VoiceSession {
  return createVoiceSession({
    ...options,
    redStore,
    env: currentRuntime(),
    permission: expoMicrophonePermission,
    tokens: createTokenSource(authedFetch),
    createAdapter: async () => createNativeRoomAdapter(),
  });
}

export {
  EXPO_GO_EXECUTION_ENVIRONMENT,
  probeVoiceTransport,
  selectVoiceTransport,
  streamingVoiceSupported,
} from "./capability";
export { DIALOGUE_WIRING, toDialogueStreamAction } from "./events";
export type { VoiceSessionEvent, VoiceSessionListener } from "./events";
export {
  EMITTED_METRIC_IDS,
  NET_JITTER_MS,
  NET_PACKET_LOSS_RATIO,
  NET_RTT_MS,
  noopMetricSink,
} from "./metrics";
export type { MetricSample, MetricSink } from "./metrics";
export { decodeRedTrigger, GENERIC_RED_SCRIPT_IDS, genericRed, resolveRed } from "./red";
export type { RedLocation, RedPresentation, RedRegister, RedScript, RedScriptCatalog } from "./red";
export { MAX_ATTEMPTS, TOKEN_REFRESH_MARGIN_MS, nextReconnect } from "./reconnect";
export { createVoiceSession } from "./session";
export type { AppLifecycle, VoiceSession, VoiceSessionDeps } from "./session";
export { createTokenSource, parseTokenResponse, voiceTokenPath } from "./token";
export type {
  RoomAdapter,
  RoomCredentials,
  SessionFailure,
  SessionPhase,
  TransportSample,
  TurnQuality,
  VoiceTransportAvailability,
  VoiceTransportKind,
  VoiceTransportStatus,
} from "./types";
