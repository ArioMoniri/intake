/**
 * The spoken dialogue's audio session, as one contract (INT-440). Pure: the
 * hook (useDialogueSession.ts) owns the expo-audio calls and hands them in.
 *
 * What it replaces, read from expo-audio 57's iOS module: the hook re-applied
 * the audio mode before EVERY clip, and every player that finished or paused
 * deactivated the AVAudioSession 100 ms after the last playable stopped
 * (`setActive(false, .notifyOthersOnDeactivation)`) — which the next clip's
 * `play()` re-activated. That toggle sat between every question and the
 * patient's turn, underneath a recorder that is meant to stay open for
 * barge-in (bargeIn.ts). The mode is now applied once per session, and the
 * dialogue's players keep the session active.
 */

/**
 * `.playAndRecord` is the only iOS category that admits capture during
 * playback, which barge-in needs; the receiver route is ruled out explicitly
 * because the same category defaults to it, and answering "the voice sounds
 * bad" with a quieter voice would be its own defect.
 */
export const DIALOGUE_AUDIO_MODE = Object.freeze({
  allowsRecording: true,
  playsInSilentMode: true,
  shouldRouteThroughEarpiece: false,
});

export type DialogueAudioMode = typeof DIALOGUE_AUDIO_MODE;

/** Every dialogue clip player keeps the session active when it pauses or ends. */
export const DIALOGUE_PLAYER_OPTIONS = Object.freeze({ keepAudioSessionActive: true });

export interface AudioModeLatch {
  /** Apply the dialogue mode unless this session already has; concurrent
   * callers share one application, and a failure is retried by the next call. */
  ensure(): Promise<void>;
}

export function createAudioModeLatch(
  apply: (mode: DialogueAudioMode) => Promise<void>,
): AudioModeLatch {
  let applied: Promise<void> | null = null;
  return {
    ensure() {
      if (applied === null) {
        const attempt = apply(DIALOGUE_AUDIO_MODE).catch((error: unknown) => {
          if (applied === attempt) {
            applied = null;
          }
          throw error;
        });
        applied = attempt;
      }
      return applied;
    },
  };
}
