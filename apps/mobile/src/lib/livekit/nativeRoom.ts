/**
 * The real LiveKit adapter (INT-103). The ONLY file under lib/livekit that
 * touches the LiveKit packages, and it reaches them exclusively through a
 * DYNAMIC import behind an injectable loader — the same shape lib/health uses
 * for HealthKit (INT-208).
 *
 * Why dynamic: `@livekit/react-native-webrtc` is a native module. In Expo Go
 * the import throws, and a throw here becomes an honest `needs_dev_build`
 * upstream instead of a red screen. In a development build it resolves and
 * the session runs for real. Either way no other module in this directory
 * imports LiveKit, so the pure logic stays testable in node.
 *
 * INVARIANT 3. The room is configured audio-only and the adapter exposes no
 * way to reach a frame: `sampleTransport` returns counters, `onData` returns
 * bytes from the DATA channel (never media), and there is no recorder, no
 * track-to-file call and no buffer. Audio frames live in the native peer
 * connection from microphone to SFU and never cross into JavaScript.
 *
 * SERVER CONTRACT (INT-090). The token grants
 * `roomJoin + canSubscribe + canPublish(sources: ["microphone"])` with
 * `canPublishData` pinned to an explicit FALSE. This client is therefore a
 * data-channel RECEIVER ONLY, which is why the adapter surface has `onData`
 * but deliberately no `publishData`. The room enables `audio/opus` alone and
 * carries no egress, ingress or recorder to write audio to.
 */
import { flattenReports, parseTransportStats } from "./stats";
import type {
  AdapterConnectionState,
  RoomAdapter,
  RoomCredentials,
  TransportSample,
} from "./types";

/**
 * The narrow slice of the LiveKit packages this adapter needs. Declaring it
 * structurally keeps `livekit-client`'s types off every other module's
 * compile path and makes the loader trivially fakeable.
 */
export interface LiveKitApi {
  /** Installs the WebRTC globals LiveKit needs. Must run before connecting. */
  registerGlobals(): void;
  /** Constructs an audio-only room. */
  createRoom(): LiveKitRoom;
}

export interface LiveKitRoom {
  connect(url: string, token: string): Promise<void>;
  disconnect(): Promise<void>;
  setMicrophoneEnabled(enabled: boolean): Promise<void>;
  /** Every audio track's stats report, local and remote. */
  statsReports(): Promise<(ReadonlyMap<string, unknown> | undefined)[]>;
  on(event: "data", listener: (payload: Uint8Array) => void): void;
  on(event: "state", listener: (state: AdapterConnectionState) => void): void;
  off(event: "data" | "state", listener: (...args: never[]) => void): void;
}

/** Structural view of the room object livekit-client hands back. */
interface RawRoom {
  connect(url: string, token: string): Promise<void>;
  disconnect(): Promise<void>;
  localParticipant: {
    setMicrophoneEnabled(enabled: boolean): Promise<unknown>;
    trackPublications: Map<string, { track?: RawTrack }>;
  };
  remoteParticipants: Map<string, { trackPublications: Map<string, { track?: RawTrack }> }>;
  on(event: string, listener: (...args: never[]) => void): unknown;
  off(event: string, listener: (...args: never[]) => void): unknown;
}

interface RawTrack {
  kind?: string;
  getRTCStatsReport?: () => Promise<ReadonlyMap<string, unknown> | undefined>;
}

/**
 * Load the real packages. Kept out of the module body so that merely
 * importing this file costs nothing and cannot throw in Expo Go.
 */
async function loadNativeLiveKitApi(): Promise<LiveKitApi> {
  const rn = await import("@livekit/react-native");
  const client = await import("livekit-client");
  return {
    registerGlobals: () => rn.registerGlobals(),
    createRoom: () => {
      // Audio-only, matching the SFU config (`audio/opus` is the sole enabled
      // codec, infra/livekit/livekit-dev.yaml). Adaptive stream and dynacast
      // are video-plane features and stay off.
      const room = new client.Room({
        adaptiveStream: false,
        dynacast: false,
      }) as unknown as RawRoom;
      return wrapRoom(room, client.RoomEvent as unknown as Record<string, string>);
    },
  };
}

function wrapRoom(room: RawRoom, events: Record<string, string>): LiveKitRoom {
  const dataEvent = events.DataReceived ?? "dataReceived";
  const stateEvent = events.ConnectionStateChanged ?? "connectionStateChanged";
  /** Keeps our listener identity stable so `off` can actually remove it. */
  const bridged = new Map<(...args: never[]) => void, (...args: never[]) => void>();

  const audioTracks = (): RawTrack[] => {
    const tracks: RawTrack[] = [];
    for (const publication of room.localParticipant.trackPublications.values()) {
      if (publication.track !== undefined) {
        tracks.push(publication.track);
      }
    }
    for (const participant of room.remoteParticipants.values()) {
      for (const publication of participant.trackPublications.values()) {
        if (publication.track !== undefined) {
          tracks.push(publication.track);
        }
      }
    }
    return tracks;
  };

  return {
    connect: (url, token) => room.connect(url, token),
    disconnect: () => room.disconnect(),
    setMicrophoneEnabled: async (enabled) => {
      await room.localParticipant.setMicrophoneEnabled(enabled);
    },
    statsReports: async () =>
      Promise.all(
        audioTracks().map((track) =>
          track.getRTCStatsReport === undefined
            ? Promise.resolve(undefined)
            : track.getRTCStatsReport().catch(() => undefined),
        ),
      ),
    on: (event: "data" | "state", listener: (...args: never[]) => void) => {
      if (event === "data") {
        const bridge = ((payload: Uint8Array) => {
          (listener as unknown as (p: Uint8Array) => void)(payload);
        }) as unknown as (...args: never[]) => void;
        bridged.set(listener, bridge);
        room.on(dataEvent, bridge);
        return;
      }
      const bridge = ((state: string) => {
        (listener as unknown as (s: AdapterConnectionState) => void)(mapConnectionState(state));
      }) as unknown as (...args: never[]) => void;
      bridged.set(listener, bridge);
      room.on(stateEvent, bridge);
    },
    off: (event, listener) => {
      const bridge = bridged.get(listener);
      if (bridge === undefined) {
        return;
      }
      bridged.delete(listener);
      room.off(event === "data" ? dataEvent : stateEvent, bridge);
    },
  } as LiveKitRoom;
}

/** livekit-client's ConnectionState strings → our three-state view. */
export function mapConnectionState(state: string): AdapterConnectionState {
  switch (state) {
    case "connected":
      return "connected";
    case "reconnecting":
    case "signalReconnecting":
      return "reconnecting";
    default:
      return "disconnected";
  }
}

/**
 * Build the adapter. `loadApi` is injectable so the wiring test can drive the
 * whole adapter with a fake and prove the shape without a native module.
 */
export function createNativeRoomAdapter(
  loadApi: () => Promise<LiveKitApi> = loadNativeLiveKitApi,
): RoomAdapter {
  let room: LiveKitRoom | null = null;

  const ensureRoom = async (): Promise<LiveKitRoom> => {
    if (room === null) {
      const api = await loadApi();
      api.registerGlobals();
      room = api.createRoom();
    }
    return room;
  };

  return {
    connect: async (credentials: RoomCredentials) => {
      const active = await ensureRoom();
      await active.connect(credentials.url, credentials.token);
      // The token's only publish grant is the microphone source, so this is
      // the one track this client can ever add.
      await active.setMicrophoneEnabled(true);
    },
    disconnect: async () => {
      if (room === null) {
        return;
      }
      const active = room;
      room = null;
      await active.disconnect();
    },
    setMicrophoneEnabled: async (enabled: boolean) => {
      if (room === null) {
        return;
      }
      await room.setMicrophoneEnabled(enabled);
    },
    sampleTransport: async (): Promise<TransportSample | null> => {
      if (room === null) {
        return null;
      }
      return parseTransportStats(flattenReports(await room.statsReports()));
    },
    onData: (listener) => {
      let attached: LiveKitRoom | null = null;
      void ensureRoom().then((active) => {
        attached = active;
        active.on("data", listener);
      });
      return () => attached?.off("data", listener as (...args: never[]) => void);
    },
    onConnectionChange: (listener) => {
      let attached: LiveKitRoom | null = null;
      void ensureRoom().then((active) => {
        attached = active;
        active.on("state", listener);
      });
      return () => attached?.off("state", listener as (...args: never[]) => void);
    },
  };
}
