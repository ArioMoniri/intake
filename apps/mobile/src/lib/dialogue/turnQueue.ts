/**
 * One turn's clips, played as ONE queue (INT-497).
 *
 * Until this, useDialogueSession played a turn's utterances — a lead-in, then
 * the question — as a chain of players: the next one created when the
 * previous one reported it had finished. Measured with the framework the
 * phone uses (scripts/voice/playback_gap.swift; docs/evidence/INT-497.md),
 * that switch alone leaves ~116 ms of dead air on AVFoundation before the
 * device's JS round trip is even added, and each expo-audio player also
 * deactivates the audio session when it finishes, which the next one then has
 * to re-activate. A single AVQueuePlayer holding both clips leaves none:
 * expo-audio's AudioPlaylist is that queue on iOS (ExoPlayer's playlist on
 * Android), and it keeps the session active between tracks.
 *
 * A clip that is made while the turn is already speaking — the question
 * behind a holding line (holdingLine.ts) — joins the same playlist, so it
 * follows without a seam; one made after the playlist ran dry is refused, and
 * the caller starts a new queue for it. A finish the player sent before an
 * append landed counts fewer tracks than the queue holds, and is not the end.
 *
 * The playlist is injected (`PlaylistFactory`), so this logic is node-tested
 * against a fake; the hook passes expo-audio's `createAudioPlaylist`. Only a
 * type is imported from expo-audio here, and types are erased.
 *
 * Barge-in (INT-233 DISTURBABLE, INT-291): `stop` pauses synchronously in the
 * same call, before anything else runs, and nothing the stopped playlist says
 * afterwards is reported.
 */
import type { AudioPlaylist, AudioPlaylistOptions } from "expo-audio";

import { createTrackClock } from "./turnTimeline";

/**
 * How often the playlist reports its status. Fine enough that the "playing"
 * caption and the timeline see a start within a tenth of a second; the
 * timeline back-dates every start by its position (turnTimeline.ts), so the
 * interval does not leak into what it measures.
 */
export const PLAYLIST_STATUS_MS = 100;

export type PlaylistFactory = (options: AudioPlaylistOptions) => AudioPlaylist;

export interface TurnQueueHooks {
  /** The clock statuses are stamped with. */
  readonly now: () => number;
  /** The queue's first audio, back-dated to when it really started. */
  readonly onStart: (at: number) => void;
  /** Dead air between two tracks of the queue, in ms. */
  readonly onJoin: (gapMs: number) => void;
  /** The last track finished. Called once. */
  readonly onFinish: () => void;
}

export interface TurnQueue {
  /** Add a clip behind the ones queued. False once the queue has finished or
   * stopped — the caller then starts a new queue. */
  append(uri: string): boolean;
  /** Stop now and free the player. Idempotent. */
  stop(): void;
  readonly finished: boolean;
}

export function playTurnQueue(
  factory: PlaylistFactory,
  uris: readonly string[],
  hooks: TurnQueueHooks,
): TurnQueue {
  const playlist = factory({
    sources: uris.map((uri) => ({ uri })),
    updateInterval: PLAYLIST_STATUS_MS,
  });
  const clock = createTrackClock();
  let started = false;
  let finished = false;
  /** Tracks this queue holds, as far as JS has told the player. */
  let queued = uris.length;
  let stopped = false;

  playlist.addListener("playlistStatusUpdate", (status) => {
    if (stopped || finished) {
      return;
    }
    const seen = clock.observe({
      index: status.currentIndex,
      positionS: status.currentTime,
      durationS: status.duration,
      playing: status.playing,
      atMs: hooks.now(),
    });
    if (seen.started !== undefined && !started) {
      started = true;
      hooks.onStart(seen.started);
    }
    if (seen.join !== undefined) {
      hooks.onJoin(seen.join);
    }
    if (status.didJustFinish && status.trackCount < queued) {
      // Runtime review: the end of an earlier track, emitted before an `add`
      // landed and delivered after it. The appended clip has not played, so
      // the turn is not over: start the player again and wait for the real end.
      playlist.play();
      return;
    }
    if (status.didJustFinish) {
      finished = true;
      hooks.onFinish();
    }
  });
  playlist.play();

  return {
    append(uri) {
      if (stopped || finished) {
        return false;
      }
      playlist.add({ uri });
      queued += 1;
      return true;
    },
    stop() {
      if (stopped) {
        return;
      }
      stopped = true;
      try {
        playlist.pause();
        playlist.destroy();
      } catch {
        // already released — nothing left to stop
      }
    },
    get finished() {
      return finished || stopped;
    },
  };
}
