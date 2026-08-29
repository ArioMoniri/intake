/** The honest capability ladder (INT-103), mirroring lib/health's (INT-208). */
import { describe, expect, it } from "vitest";

import {
  EXPO_GO_EXECUTION_ENVIRONMENT,
  probeVoiceTransport,
  selectVoiceTransport,
  streamingVoiceSupported,
} from "./capability";

describe("selectVoiceTransport", () => {
  it("serves LiveKit in a development or store build on a phone", () => {
    for (const os of ["ios", "android"]) {
      for (const environment of ["standalone", "bare"]) {
        expect(selectVoiceTransport({ os, executionEnvironment: environment })).toBe("livekit");
      }
    }
  });

  it("degrades to the honest stub in Expo Go, on both platforms", () => {
    for (const os of ["ios", "android"]) {
      expect(
        selectVoiceTransport({ os, executionEnvironment: EXPO_GO_EXECUTION_ENVIRONMENT }),
      ).toBe("expo_go_stub");
    }
  });

  it("is unsupported off a phone", () => {
    expect(selectVoiceTransport({ os: "web", executionEnvironment: "bare" })).toBe("unsupported");
    expect(selectVoiceTransport({ os: "macos", executionEnvironment: "standalone" })).toBe(
      "unsupported",
    );
  });

  it("treats Expo Go on an unsupported platform as unsupported, not needs_dev_build", () => {
    // A dev build would not help on web: there is no native module to load.
    expect(
      selectVoiceTransport({ os: "web", executionEnvironment: EXPO_GO_EXECUTION_ENVIRONMENT }),
    ).toBe("unsupported");
  });
});

describe("probeVoiceTransport", () => {
  it("names a tr resource key for every status rather than a raw sentence", () => {
    const statuses = [
      probeVoiceTransport({ os: "ios", executionEnvironment: "standalone" }),
      probeVoiceTransport({ os: "ios", executionEnvironment: EXPO_GO_EXECUTION_ENVIRONMENT }),
      probeVoiceTransport({ os: "web", executionEnvironment: "bare" }),
    ];
    expect(statuses.map((s) => s.status)).toEqual([
      "ok",
      "needs_dev_build",
      "platform_unsupported",
    ]);
    for (const availability of statuses) {
      expect(availability.messageKey).toMatch(/^voice\.transport\./);
    }
  });
});

describe("streamingVoiceSupported", () => {
  it("is the single gate the session consults", () => {
    expect(streamingVoiceSupported({ os: "android", executionEnvironment: "standalone" })).toBe(
      true,
    );
    expect(
      streamingVoiceSupported({
        os: "android",
        executionEnvironment: EXPO_GO_EXECUTION_ENVIRONMENT,
      }),
    ).toBe(false);
  });
});
