/**
 * INT-559 — where the microphone may be open while the agent speaks.
 *
 * expo-audio's AudioStream puts the iOS audio session in the `.record`
 * category, which silences playback. So on iOS the clip and the microphone
 * cannot be open together: the clip plays tap-interruptible, and the
 * microphone opens when the turn becomes the patient's. Android's AudioRecord
 * has no such category, so INT-291's barge-in-by-voice keeps its microphone.
 */
import { describe, expect, it } from "vitest";

import { micMayOpenWhileSpeaking } from "./policy";

describe("micMayOpenWhileSpeaking", () => {
  it("is refused on iOS, where the stream's session category silences the clip", () => {
    expect(micMayOpenWhileSpeaking("ios")).toBe(false);
  });

  it("is allowed on Android", () => {
    expect(micMayOpenWhileSpeaking("android")).toBe(true);
  });

  it("is allowed anywhere else the app could run", () => {
    expect(micMayOpenWhileSpeaking("web")).toBe(true);
    expect(micMayOpenWhileSpeaking("macos")).toBe(true);
  });
});
