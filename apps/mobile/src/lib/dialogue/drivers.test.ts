/**
 * INT-551 (the RED-UI review of #842, item 3): no dialogue driver reaches the
 * microphone or the speaker once the dialogue has closed (CLAUDE.md
 * invariants 9 and 21; INT-446, INT-465).
 *
 * Under a RED the patient sees, DialogueIntake calls `leave`, and the turn
 * never moves again: the stream freezes where the RED landed. Each driver used
 * to ask only whether its own turn had moved on, so a RED that landed while a
 * clip was being made let that clip play, and the barge-in watch then opened
 * the microphone under the RED. A RED can land in any await; these tests hold
 * each one open, land the RED there, and let it go.
 *
 * The device is a fake that logs every call: drivers.ts takes the recorder,
 * the player and the audio session as functions (useDialogueSession.ts adapts
 * expo-audio to them), so nothing here needs a microphone.
 */
import { describe, expect, it } from "vitest";

import {
  closeDialogue,
  openMicrophone,
  speakTurn,
  watchMayArm,
  type DialogueClosing,
  type MicrophonePort,
  type SpokenTurnPort,
} from "./drivers";

interface Deferred<T> {
  readonly promise: Promise<T>;
  resolve(value: T): void;
  reject(reason: unknown): void;
}

function deferred<T = void>(): Deferred<T> {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

/** Lets every pending continuation run, so a driver reaches its next await. */
async function settle(): Promise<void> {
  for (let i = 0; i < 10; i += 1) {
    await Promise.resolve();
  }
}

/** A dialogue that a RED can close at any moment. */
function dialogue() {
  const life = { closed: false };
  return {
    life,
    closed: () => life.closed,
    /** The RED: DialogueIntake's effect calls `leave`, which sets the flag first. */
    red: () => {
      life.closed = true;
    },
  };
}

interface FakeMicrophone extends MicrophonePort {
  readonly calls: string[];
  recording: boolean;
}

/** A recorder that logs each call; a held step waits for its promise. */
function microphone(
  hold: { allowRecording?: Promise<void>; prepare?: Promise<void> } = {},
): FakeMicrophone {
  const calls: string[] = [];
  const mic: FakeMicrophone = {
    calls,
    recording: false,
    isRecording: () => mic.recording,
    allowRecording: async () => {
      calls.push("allowRecording");
      await hold.allowRecording;
    },
    prepare: async () => {
      calls.push("prepare");
      await hold.prepare;
    },
    record: () => {
      calls.push("record");
      mic.recording = true;
    },
  };
  return mic;
}

const CLIPS = ["lead.m4a", "question.m4a"] as const;

/** One agent turn's audio, logged; a held step waits for its promise. */
function turn(hold: { prepare?: Promise<readonly string[]>; allowPlayback?: Promise<void> } = {}) {
  const calls: string[] = [];
  const port: SpokenTurnPort<readonly string[]> = {
    prepare: async () => {
      calls.push("prepare");
      return hold.prepare ?? CLIPS;
    },
    show: () => {
      calls.push("show");
    },
    allowPlayback: async () => {
      calls.push("allowPlayback");
      await hold.allowPlayback;
    },
    play: (clips) => {
      calls.push(`play:${clips.join("+")}`);
    },
    watch: async () => {
      calls.push("watch");
    },
    unavailable: () => {
      calls.push("unavailable");
    },
  };
  return { port, calls };
}

describe("openMicrophone: the one way a driver opens the microphone", () => {
  it("positive control: the session that admits capture, one prepare, then record", async () => {
    const { closed } = dialogue();
    const mic = microphone();
    expect(await openMicrophone(mic, closed)).toBe(true);
    expect(mic.calls).toEqual(["allowRecording", "prepare", "record"]);
    expect(mic.recording).toBe(true);
  });

  it("a closed dialogue opens nothing", async () => {
    const d = dialogue();
    d.red();
    const mic = microphone();
    expect(await openMicrophone(mic, d.closed)).toBe(false);
    expect(mic.calls).toEqual([]);
  });

  it("a RED landing while the audio session switches: the recorder is never prepared", async () => {
    const d = dialogue();
    const hold = deferred();
    const mic = microphone({ allowRecording: hold.promise });
    const opening = openMicrophone(mic, d.closed);
    await settle();
    d.red();
    hold.resolve();
    expect(await opening).toBe(false);
    expect(mic.calls).toEqual(["allowRecording"]);
    expect(mic.recording).toBe(false);
  });

  it("a RED landing while the recorder prepares: it is prepared, never started", async () => {
    const d = dialogue();
    const hold = deferred();
    const mic = microphone({ prepare: hold.promise });
    const opening = openMicrophone(mic, d.closed);
    await settle();
    expect(mic.calls).toEqual(["allowRecording", "prepare"]);
    d.red();
    hold.resolve();
    expect(await opening).toBe(false);
    expect(mic.calls).toEqual(["allowRecording", "prepare"]);
    expect(mic.recording).toBe(false);
  });
});

describe("speakTurn: RED landing mid-clip-prepare", () => {
  it("positive control: a live turn makes its clips, shows them, switches the session, plays, then watches", async () => {
    const { closed } = dialogue();
    const spoken = turn();
    expect(await speakTurn(spoken.port, closed)).toBe("spoken");
    expect(spoken.calls).toEqual([
      "prepare",
      "show",
      "allowPlayback",
      "play:lead.m4a+question.m4a",
      "watch",
    ]);
  });

  it("the clip made after the RED never plays, and nothing watches the microphone", async () => {
    const d = dialogue();
    const clips = deferred<readonly string[]>();
    const spoken = turn({ prepare: clips.promise });
    const speaking = speakTurn(spoken.port, d.closed);
    await settle();
    d.red();
    clips.resolve(CLIPS);
    expect(await speaking).toBe("halted");
    expect(spoken.calls).toEqual(["prepare"]);
  });

  it("a clip that fails after the RED dispatches nothing into the closed dialogue", async () => {
    const d = dialogue();
    const clips = deferred<readonly string[]>();
    const spoken = turn({ prepare: clips.promise });
    const speaking = speakTurn(spoken.port, d.closed);
    await settle();
    d.red();
    clips.reject(new Error("tts lane timed out"));
    expect(await speaking).toBe("halted");
    expect(spoken.calls).toEqual(["prepare"]);
  });

  it("a RED landing while the session switches to play-and-record: nothing plays", async () => {
    const d = dialogue();
    const mode = deferred();
    const spoken = turn({ allowPlayback: mode.promise });
    const speaking = speakTurn(spoken.port, d.closed);
    await settle();
    d.red();
    mode.resolve();
    expect(await speaking).toBe("halted");
    expect(spoken.calls).toEqual(["prepare", "show", "allowPlayback"]);
  });

  it("near miss: with no RED, a clip that fails goes on silently (speech_unavailable)", async () => {
    const { closed } = dialogue();
    const clips = deferred<readonly string[]>();
    const spoken = turn({ prepare: clips.promise });
    const speaking = speakTurn(spoken.port, closed);
    clips.reject(new Error("tts lane timed out"));
    expect(await speaking).toBe("unavailable");
    expect(spoken.calls).toEqual(["prepare", "unavailable"]);
  });

  it("a turn that moved on halts the same way (the stale guard it always had)", async () => {
    let stale = false;
    const clips = deferred<readonly string[]>();
    const spoken = turn({ prepare: clips.promise });
    const speaking = speakTurn(spoken.port, () => stale);
    await settle();
    stale = true;
    clips.resolve(CLIPS);
    expect(await speaking).toBe("halted");
    expect(spoken.calls).toEqual(["prepare"]);
  });
});

describe("watchMayArm: RED landing mid-speaking", () => {
  it("positive control: the speaking turn's open microphone is watched, not opened again", async () => {
    const { closed } = dialogue();
    const mic = microphone();
    mic.recording = true;
    expect(await watchMayArm(mic, { halted: closed, closed })).toBe(true);
    expect(mic.calls).toEqual([]);
  });

  it("opens the microphone when the turn has not, then arms", async () => {
    const { closed } = dialogue();
    const mic = microphone();
    expect(await watchMayArm(mic, { halted: closed, closed })).toBe(true);
    expect(mic.calls).toEqual(["allowRecording", "prepare", "record"]);
  });

  it("a RED landing while the watch opens the microphone: it never records, and no watch arms", async () => {
    const d = dialogue();
    const hold = deferred();
    const mic = microphone({ prepare: hold.promise });
    const arming = watchMayArm(mic, { halted: d.closed, closed: d.closed });
    await settle();
    d.red();
    hold.resolve();
    expect(await arming).toBe(false);
    expect(mic.calls).toEqual(["allowRecording", "prepare"]);
    expect(mic.recording).toBe(false);
  });

  it("a microphone that fails to open costs barge-in and nothing else", async () => {
    const { closed } = dialogue();
    const hold = deferred();
    const mic = microphone({ prepare: hold.promise });
    const arming = watchMayArm(mic, { halted: closed, closed });
    hold.reject(new Error("recorder busy"));
    expect(await arming).toBe(false);
  });

  it("near miss: a turn that moved on while the microphone opened arms no watch, but keeps the recording", async () => {
    let stale = false;
    const { closed } = dialogue();
    const hold = deferred();
    const mic = microphone({ prepare: hold.promise });
    const arming = watchMayArm(mic, { halted: () => stale || closed(), closed });
    await settle();
    stale = true; // a barge-in: the recording that heard it is the patient's answer
    hold.resolve();
    expect(await arming).toBe(false);
    expect(mic.recording).toBe(true);
  });

  it("RED mid-speaking, end to end: the clip plays, the RED lands while the watch opens the microphone, and it stays closed", async () => {
    const d = dialogue();
    const hold = deferred();
    const mic = microphone({ prepare: hold.promise });
    const spoken = turn();
    let armed: boolean | null = null;
    const port: SpokenTurnPort<readonly string[]> = {
      ...spoken.port,
      watch: async () => {
        armed = await watchMayArm(mic, { halted: d.closed, closed: d.closed });
      },
    };
    const speaking = speakTurn(port, d.closed);
    await settle();
    expect(spoken.calls).toContain("play:lead.m4a+question.m4a");
    // DialogueIntake's effect: leave() closes the dialogue. The recorder is
    // still preparing, so there is nothing for it to stop yet.
    const closing = recordedClosing({ recording: mic.recording, listening: false });
    await closeDialogue({ ...closing.port, markClosed: d.red });
    expect(closing.calls).not.toContain("stopAndDiscard");
    hold.resolve();
    await speaking;
    expect(mic.calls).toEqual(["allowRecording", "prepare"]);
    expect(mic.recording).toBe(false);
    expect(armed).toBe(false);
  });
});

/** The close, logged. */
function recordedClosing(state: { recording: boolean; listening: boolean }) {
  const calls: string[] = [];
  const port: DialogueClosing = {
    markClosed: () => {
      calls.push("markClosed");
    },
    stopWatch: () => {
      calls.push("stopWatch");
    },
    stopPlayback: () => {
      calls.push("stopPlayback");
    },
    abort: () => {
      calls.push("abort");
    },
    recording: () => state.recording,
    listening: () => state.listening,
    stopAndDiscard: async () => {
      calls.push("stopAndDiscard");
    },
    clearClips: async () => {
      calls.push("clearClips");
    },
  };
  return { port, calls };
}

describe("closeDialogue: what leave() does when a RED lands", () => {
  it("RED mid-speaking with the barge-in microphone open: it is stopped and its recording discarded", async () => {
    const closing = recordedClosing({ recording: true, listening: false });
    await closeDialogue(closing.port);
    expect(closing.calls).toEqual([
      "markClosed",
      "stopWatch",
      "stopPlayback",
      "abort",
      "stopAndDiscard",
      "clearClips",
    ]);
  });

  it("RED while listening, the microphone still opening: it is stopped too", async () => {
    const closing = recordedClosing({ recording: false, listening: true });
    await closeDialogue(closing.port);
    expect(closing.calls).toContain("stopAndDiscard");
  });

  it("near miss: on a silent confirm turn with the microphone closed there is nothing to stop", async () => {
    const closing = recordedClosing({ recording: false, listening: false });
    await closeDialogue(closing.port);
    expect(closing.calls).not.toContain("stopAndDiscard");
    expect(closing.calls).toContain("clearClips");
  });

  it("the flag comes first, so a driver past any await reads it before it acts", async () => {
    const closing = recordedClosing({ recording: true, listening: true });
    await closeDialogue(closing.port);
    expect(closing.calls[0]).toBe("markClosed");
  });
});
