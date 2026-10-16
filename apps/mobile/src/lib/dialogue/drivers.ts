/**
 * The dialogue's audio drivers, as steps a closed dialogue cannot take
 * (INT-551; CLAUDE.md invariants 9 and 21; INT-446, INT-465).
 *
 * The dialogue closes when a RED the patient sees stands (DialogueIntake calls
 * `leave`), and on every terminal turn. A RED can land while a driver waits:
 * on the clip being made, on the audio session switching, on the recorder
 * preparing. Each driver used to ask only whether its own turn had moved on,
 * and under a RED the turn never moves (the stream freezes where the RED
 * landed), so a clip made after the RED still played and the barge-in watch
 * still opened the microphone.
 *
 * So every step here reads the dialogue's state after each await, before it
 * acts, and a closed dialogue ends the step where it stands. Nothing here
 * imports expo-audio: the recorder, the player and the audio session arrive
 * as functions, which useDialogueSession.ts adapts from the device, so every
 * interleaving is node-tested (drivers.test.ts).
 */

/** The microphone, as the drivers reach it. */
export interface MicrophonePort {
  /** The recorder reports it is capturing now. */
  isRecording(): boolean;
  /** Switch the audio session to one that admits capture. */
  allowRecording(): Promise<void>;
  /** Prepare the recorder: one per turn. */
  prepare(): Promise<void>;
  /** Start capturing. */
  record(): void;
}

/**
 * Open the microphone, unless the dialogue closes first. Resolves to whether
 * it is recording. A dialogue that closes while the session switches or the
 * recorder prepares is left prepared and silent: `record` is never called.
 * A device failure rejects, as it always did; the caller decides what it costs.
 */
export async function openMicrophone(mic: MicrophonePort, closed: () => boolean): Promise<boolean> {
  if (closed()) {
    return false;
  }
  await mic.allowRecording();
  if (closed()) {
    return false;
  }
  await mic.prepare();
  if (closed()) {
    return false;
  }
  mic.record();
  return true;
}

/** One agent turn's audio, as the speaking driver runs it. */
export interface SpokenTurnPort<Clips> {
  /** Make the turn's clips (the clip prepare). Rejects on an output failure. */
  prepare(): Promise<Clips>;
  /** The clips are made and the turn stands: the transcript shows what will be said. */
  show(clips: Clips): void;
  /** Switch the audio session to play-and-record, so the patient can cut in. */
  allowPlayback(): Promise<void>;
  /** Start the clips, in order. */
  play(clips: Clips): void;
  /** Watch the microphone for a barge-in while the clips play. */
  watch(): Promise<void>;
  /** Audio output failed while the turn stood: the conversation goes on, silent. */
  unavailable(): void;
}

export type SpokenTurnOutcome = "spoken" | "halted" | "unavailable";

/**
 * Speak one turn. `halted` is true once the turn has moved on or the dialogue
 * has closed. It is read after every await, so a RED that lands while the
 * clip is being made, or while the session switches, plays nothing, watches
 * nothing and dispatches nothing into the closed dialogue.
 */
export async function speakTurn<Clips>(
  turn: SpokenTurnPort<Clips>,
  halted: () => boolean,
): Promise<SpokenTurnOutcome> {
  try {
    const clips = await turn.prepare();
    if (halted()) {
      return "halted";
    }
    turn.show(clips);
    await turn.allowPlayback();
    if (halted()) {
      return "halted";
    }
    turn.play(clips);
    await turn.watch();
    return "spoken";
  } catch {
    if (halted()) {
      return "halted";
    }
    turn.unavailable();
    return "unavailable";
  }
}

/** What a driver asks before it acts: its turn has moved on, or the dialogue closed. */
export interface DriverLife {
  /** The turn moved on, or the dialogue closed. */
  halted(): boolean;
  /** The dialogue closed (a RED, a leave, a terminal turn). */
  closed(): boolean;
}

/**
 * Whether the barge-in watch may arm for the clip now playing. The microphone
 * is opened here when the turn has not opened it, and never once the dialogue
 * has closed. A turn that moved on while it opened arms no watch, but keeps
 * the recording: the words that interrupted are the patient's answer. A
 * microphone that fails to open costs barge-in and nothing else, so the turn
 * goes on, interruptible by a tap.
 */
export async function watchMayArm(mic: MicrophonePort, life: DriverLife): Promise<boolean> {
  if (!mic.isRecording()) {
    try {
      if (!(await openMicrophone(mic, life.closed))) {
        return false;
      }
    } catch {
      return false;
    }
  }
  return !life.halted();
}

/** What `leave` stops, in the order it stops it. */
export interface DialogueClosing {
  /** Set the flag every driver reads after each await. */
  markClosed(): void;
  stopWatch(): void;
  stopPlayback(): void;
  abort(): void;
  /** The recorder is capturing: the speaking turn opens it for barge-in. */
  recording(): boolean;
  /** The turn is the patient's: its microphone may still be opening. */
  listening(): boolean;
  /** Stop the recorder and delete what it captured (invariant 3's posture). */
  stopAndDiscard(): Promise<void>;
  clearClips(): Promise<void>;
}

/**
 * Close the dialogue. The flag comes first, so any driver past an await reads
 * it before it acts. Whatever microphone is open is stopped and its recording
 * discarded, the speaking turn's barge-in microphone included; before INT-551
 * only a listening turn's was, so a RED that landed while the agent spoke
 * left the microphone recording under it.
 */
export async function closeDialogue(closing: DialogueClosing): Promise<void> {
  closing.markClosed();
  closing.stopWatch();
  closing.stopPlayback();
  closing.abort();
  if (closing.recording() || closing.listening()) {
    await closing.stopAndDiscard();
  }
  await closing.clearClips();
}
