/**
 * Where the microphone may be open while the agent speaks (INT-559).
 *
 * INT-291 opens the microphone when the agent STARTS speaking so a patient
 * can cut in by voice. expo-audio's AudioStream — the file-less capture this
 * app uses — puts the iOS audio session in the `.record` category when it
 * starts, and that category silences playback. So on iOS the clip and the
 * microphone cannot be open together: the clip plays tap-interruptible, as
 * it did before INT-291, and the microphone opens when the turn becomes the
 * patient's. Android's AudioRecord has no session category, so the barge-in
 * microphone keeps its place there. Restoring voice barge-in on iOS needs
 * either an upstream option on the stream's session category or a local
 * module, and is recorded as such in docs/evidence/INT-559.md.
 */
export function micMayOpenWhileSpeaking(os: string): boolean {
  return os !== "ios";
}
