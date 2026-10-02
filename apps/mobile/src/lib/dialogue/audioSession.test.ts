/**
 * INT-440 — one audio session for the whole spoken dialogue.
 *
 * Measured in expo-audio 57's iOS module: every clip re-applied the audio
 * mode, and every player that finished or paused DEACTIVATED the session
 * (`setActive(false, .notifyOthersOnDeactivation)`, 100 ms after the last
 * playable stopped) — which the next clip's `play()` then re-activated. That
 * toggle sat between every question and the patient's turn, under a recorder
 * that was meant to stay open for barge-in. The mode is now applied once per
 * session, and the dialogue's players keep the session active.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it, vi } from "vitest";

import { createAudioModeLatch, DIALOGUE_AUDIO_MODE, DIALOGUE_PLAYER_OPTIONS } from "./audioSession";

describe("the dialogue's audio contract", () => {
  it("plays and records at once, on the loudspeaker, in silent mode", () => {
    // `.playAndRecord` is the only iOS category that admits capture during
    // playback (barge-in); the receiver would answer "the voice sounds bad"
    // with a quieter voice.
    expect(DIALOGUE_AUDIO_MODE).toEqual({
      allowsRecording: true,
      playsInSilentMode: true,
      shouldRouteThroughEarpiece: false,
    });
  });

  it("keeps the session active between clips", () => {
    expect(DIALOGUE_PLAYER_OPTIONS).toEqual({ keepAudioSessionActive: true });
  });
});

describe("createAudioModeLatch — the mode is applied once per session", () => {
  it("applies on the first ensure and never again", async () => {
    const apply = vi.fn(async () => undefined);
    const latch = createAudioModeLatch(apply);
    await latch.ensure();
    await latch.ensure();
    await latch.ensure();
    expect(apply).toHaveBeenCalledTimes(1);
    expect(apply).toHaveBeenCalledWith(DIALOGUE_AUDIO_MODE);
  });

  it("shares one application between concurrent callers", async () => {
    let release: () => void = () => undefined;
    const apply = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          release = resolve;
        }),
    );
    const latch = createAudioModeLatch(apply);
    const both = Promise.all([latch.ensure(), latch.ensure()]);
    release();
    await both;
    expect(apply).toHaveBeenCalledTimes(1);
  });

  it("retries after a failure instead of caching it", async () => {
    const apply = vi
      .fn<(mode: typeof DIALOGUE_AUDIO_MODE) => Promise<void>>()
      .mockRejectedValueOnce(new Error("session_busy"))
      .mockResolvedValue(undefined);
    const latch = createAudioModeLatch(apply);
    await expect(latch.ensure()).rejects.toThrow("session_busy");
    await latch.ensure();
    await latch.ensure();
    expect(apply).toHaveBeenCalledTimes(2);
  });
});

describe("the session hook uses the contract (INT-440)", () => {
  const hook = readFileSync(
    join(fileURLToPath(new URL(".", import.meta.url)), "useDialogueSession.ts"),
    "utf8",
  );

  it("sets the audio mode only through the latch", () => {
    expect(hook.match(/setAudioModeAsync\(/g) ?? []).toHaveLength(1);
    expect(hook).toMatch(
      /createAudioModeLatch\(\s*\(mode\) => AudioModule\.setAudioModeAsync\(mode\)/,
    );
  });

  it("plays a bundled clip before it asks any lane to synthesize (INT-440 fast path)", () => {
    const speaking = hook.slice(
      hook.indexOf("const speaking ="),
      hook.indexOf("// Listening driver"),
    );
    const bundled = speaking.indexOf("bundledClipFor(");
    const ensure = speaking.indexOf("store.ensure(");
    expect(bundled).toBeGreaterThan(-1);
    expect(ensure).toBeGreaterThan(bundled);
  });

  it("creates every clip player with the keep-active options", () => {
    const players = hook.match(/createAudioPlayer\([^)]*\)/g) ?? [];
    expect(players.length).toBeGreaterThan(0);
    for (const call of players) {
      expect(call).toContain("DIALOGUE_PLAYER_OPTIONS");
    }
  });
});
