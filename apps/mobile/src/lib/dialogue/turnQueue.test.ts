/**
 * INT-497 — one turn's clips play as ONE queue, so there is no player switch
 * between them.
 *
 * Measured with the same framework the phone uses (scripts/voice/
 * playback_gap.swift, docs/evidence/INT-497.md): a new AVPlayer created when
 * the previous one finishes leaves ~116 ms of dead air before the next clip;
 * one AVQueuePlayer holding both leaves none. expo-audio's AudioPlaylist is
 * that queue on iOS. These tests drive the queue logic against a fake
 * playlist, because the suite runs in node (the hook passes the real one).
 */
import { describe, expect, it } from "vitest";

import type { AudioPlaylistStatus } from "expo-audio";

import { PLAYLIST_STATUS_MS, playTurnQueue, type PlaylistFactory } from "./turnQueue";

class FakePlaylist {
  sources: { uri: string }[];
  played = 0;
  paused = 0;
  destroyed = false;
  updateInterval: number;
  private listeners: ((status: AudioPlaylistStatus) => void)[] = [];

  constructor(sources: { uri: string }[], updateInterval: number) {
    this.sources = [...sources];
    this.updateInterval = updateInterval;
  }

  add(source: { uri: string }) {
    this.sources.push(source);
  }

  play() {
    this.played += 1;
  }

  pause() {
    this.paused += 1;
  }

  destroy() {
    this.destroyed = true;
  }

  addListener(_event: "playlistStatusUpdate", listener: (status: AudioPlaylistStatus) => void) {
    this.listeners.push(listener);
    return { remove: () => undefined };
  }

  emit(partial: Partial<AudioPlaylistStatus>) {
    const status = {
      id: "p",
      currentIndex: 0,
      trackCount: this.sources.length,
      currentTime: 0,
      duration: 1,
      playing: true,
      isBuffering: false,
      isLoaded: true,
      playbackRate: 1,
      muted: false,
      volume: 1,
      loop: "none",
      didJustFinish: false,
      ...partial,
    } as AudioPlaylistStatus;
    this.listeners.forEach((listener) => listener(status));
  }
}

function harness(uris: string[]) {
  const made: FakePlaylist[] = [];
  const factory: PlaylistFactory = (options) => {
    const playlist = new FakePlaylist(
      options.sources as { uri: string }[],
      options.updateInterval ?? 0,
    );
    made.push(playlist);
    return playlist as unknown as ReturnType<PlaylistFactory>;
  };
  const events: string[] = [];
  let now = 0;
  const queue = playTurnQueue(factory, uris, {
    now: () => now,
    onStart: (at) => events.push(`start@${at}`),
    onJoin: (gap) => events.push(`join:${gap}`),
    onFinish: () => events.push("finish"),
  });
  return {
    queue,
    playlist: made[0],
    events,
    at: (ms: number) => {
      now = ms;
    },
  };
}

describe("playTurnQueue — one playlist for the whole turn", () => {
  it("queues every clip of the turn in one playlist and starts it at once", () => {
    const h = harness(["file:///lead", "file:///question"]);
    expect(h.playlist.sources).toEqual([{ uri: "file:///lead" }, { uri: "file:///question" }]);
    expect(h.playlist.played).toBe(1);
    expect(h.playlist.updateInterval).toBe(PLAYLIST_STATUS_MS);
  });

  it("reports the turn's first audio once, back-dated by the position", () => {
    const h = harness(["file:///q"]);
    h.at(1_100);
    h.playlist.emit({ currentIndex: 0, currentTime: 0.1, duration: 1.5 });
    h.at(1_300);
    h.playlist.emit({ currentIndex: 0, currentTime: 0.3, duration: 1.5 });
    expect(h.events).toEqual(["start@1000"]);
  });

  it("reports the dead air between two tracks", () => {
    const h = harness(["file:///lead", "file:///q"]);
    h.at(1_100);
    h.playlist.emit({ currentIndex: 0, currentTime: 0.1, duration: 1.0 });
    h.at(2_050);
    h.playlist.emit({ currentIndex: 1, currentTime: 0.05, duration: 2.0 });
    expect(h.events).toEqual(["start@1000", "join:0"]);
  });

  it("finishes once, when the last track finishes", () => {
    const h = harness(["file:///lead", "file:///q"]);
    h.playlist.emit({ didJustFinish: true, playing: false, currentIndex: 1 });
    h.playlist.emit({ didJustFinish: true, playing: false, currentIndex: 1 });
    expect(h.events.filter((event) => event === "finish")).toHaveLength(1);
    expect(h.queue.finished).toBe(true);
  });
});

describe("playTurnQueue — a clip that arrives while the turn is speaking", () => {
  it("joins the same playlist, so the late question follows the holding line gaplessly", () => {
    const h = harness(["file:///holding"]);
    expect(h.queue.append("file:///q")).toBe(true);
    expect(h.playlist.sources).toEqual([{ uri: "file:///holding" }, { uri: "file:///q" }]);
  });

  it("refuses once the playlist has finished — the caller starts a new one", () => {
    const h = harness(["file:///holding"]);
    h.playlist.emit({ didJustFinish: true, playing: false });
    expect(h.queue.append("file:///q")).toBe(false);
    expect(h.playlist.sources).toHaveLength(1);
  });

  it("never drops an appended question for a finish the player sent before the append", () => {
    // Runtime review: the native end of the holding line can be emitted before
    // `add` lands and arrive after it. That finish counts one track fewer than
    // the queue now holds — it is stale: the question still plays and the turn
    // is not over.
    const h = harness(["file:///holding"]);
    expect(h.queue.append("file:///q")).toBe(true);
    h.playlist.emit({ didJustFinish: true, playing: false, currentIndex: 0, trackCount: 1 });
    expect(h.events).not.toContain("finish");
    expect(h.queue.finished).toBe(false);
    expect(h.playlist.played).toBe(2); // started again, so the question plays
    h.playlist.emit({ didJustFinish: true, playing: false, currentIndex: 1, trackCount: 2 });
    expect(h.events).toContain("finish");
  });
});

describe("playTurnQueue — stop is immediate and final (the barge-in guarantee)", () => {
  it("pauses and frees the playlist in the same call", () => {
    const h = harness(["file:///q"]);
    h.queue.stop();
    expect(h.playlist.paused).toBe(1);
    expect(h.playlist.destroyed).toBe(true);
  });

  it("reports nothing after it was stopped", () => {
    const h = harness(["file:///q"]);
    h.queue.stop();
    h.playlist.emit({ currentTime: 0.2 });
    h.playlist.emit({ didJustFinish: true, playing: false });
    expect(h.events).toEqual([]);
    expect(h.queue.append("file:///late")).toBe(false);
  });

  it("is safe to call twice", () => {
    const h = harness(["file:///q"]);
    h.queue.stop();
    h.queue.stop();
    expect(h.playlist.paused).toBe(1);
  });
});
