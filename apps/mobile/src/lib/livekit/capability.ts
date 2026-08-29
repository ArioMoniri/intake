/**
 * Voice-transport capability probe (INT-103), mirroring lib/health's ladder
 * (INT-208) because the honesty problem is identical: a native module that
 * CANNOT exist in Expo Go, and a UI that must say so rather than pretend.
 *
 * LiveKit needs `@livekit/react-native-webrtc`, a native peer-connection
 * module. Expo Go ships a fixed set of native modules and cannot load it — no
 * amount of JS makes a WebRTC stack appear there. So in Expo Go this probe
 * returns `needs_dev_build` and the streaming voice path refuses to start.
 *
 * What it must NEVER do is degrade quietly into the dev-tier record→upload
 * loop and let the patient believe they are in the real session. Invariant 17
 * forbids the fake; the typed refusal below is the alternative.
 *
 * Pure by construction: the runtime facts arrive as arguments, so the whole
 * matrix is unit-tested in node with no Expo runtime present.
 */
import type {
  RuntimeEnvironment,
  VoiceTransportAvailability,
  VoiceTransportKind,
  VoiceTransportStatus,
} from "./types";

/** Constants.executionEnvironment value that identifies Expo Go. */
export const EXPO_GO_EXECUTION_ENVIRONMENT = "storeClient";

export function selectVoiceTransport(env: RuntimeEnvironment): VoiceTransportKind {
  if (env.os !== "ios" && env.os !== "android") {
    // Web and anything else: there is no LiveKit RN native module to load.
    return "unsupported";
  }
  if (env.executionEnvironment === EXPO_GO_EXECUTION_ENVIRONMENT) {
    return "expo_go_stub";
  }
  return "livekit";
}

/** The resource key carrying the honest explanation for each status. */
const MESSAGE_KEYS: Readonly<Record<VoiceTransportStatus, string>> = {
  ok: "voice.transport.ok",
  needs_dev_build: "voice.transport.needsDevBuild",
  platform_unsupported: "voice.transport.unsupported",
  permission_denied: "voice.transport.micDenied",
};

export function availabilityFor(status: VoiceTransportStatus): VoiceTransportAvailability {
  return { status, messageKey: MESSAGE_KEYS[status] };
}

/**
 * The capability answer for a runtime, before any permission is requested.
 * `livekit` is reported as `ok` only in the sense that the transport EXISTS
 * here — the microphone grant is a separate gate the session applies next.
 */
export function probeVoiceTransport(env: RuntimeEnvironment): VoiceTransportAvailability {
  switch (selectVoiceTransport(env)) {
    case "livekit":
      return availabilityFor("ok");
    case "expo_go_stub":
      return availabilityFor("needs_dev_build");
    case "unsupported":
      return availabilityFor("platform_unsupported");
  }
}

/** True only where the streaming session may actually be attempted. */
export function streamingVoiceSupported(env: RuntimeEnvironment): boolean {
  return selectVoiceTransport(env) === "livekit";
}
