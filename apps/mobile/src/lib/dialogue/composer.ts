/**
 * The chat composer's trailing control (INT-462; docs/design/library-patterns.md
 * P1 and P3).
 *
 * Pure, so lib/dialogue/composer.test.ts holds the whole rule. The composer is
 * one capsule with one control inside its trailing edge, as Messages, ChatGPT
 * and Perplexity draw it: a mic while the draft is empty, send once there are
 * words. The owner said yes to the mic on 3 Oct 2026, on two conditions this
 * rule carries: it opens the microphone only when tapped (the rule returns
 * which path a tap takes; nothing calls it on its own), and it changes nothing
 * about RED, which paints as a root layer above this screen.
 *
 * The mic uses the session's existing paths, so the turn machine is the one
 * that decides what listening means: a tap while the agent speaks is a
 * barge-in, and a tap on the confirm turn is the spoken correction. While the
 * patient is already talking the control is stop ("Bitirdim"); while the
 * dialogue settles there is no live question, so it is a disabled send.
 * The swap is a state change with no motion (ADR-033 forbids a morph).
 */

/** The turn phases the composer is on screen for. */
export type ComposerPhase = "speaking" | "listening" | "confirming" | "settling";

export type ComposerTrailing =
  | { readonly kind: "send"; readonly enabled: boolean }
  | { readonly kind: "mic"; readonly opens: "bargeIn" | "speakCorrection" }
  | { readonly kind: "stop" };

export function composerTrailing({
  draft,
  phase,
}: {
  readonly draft: string;
  readonly phase: ComposerPhase;
}): ComposerTrailing {
  if (draft.trim().length > 0) {
    return { kind: "send", enabled: true };
  }
  switch (phase) {
    case "speaking":
      return { kind: "mic", opens: "bargeIn" };
    case "confirming":
      return { kind: "mic", opens: "speakCorrection" };
    case "listening":
      return { kind: "stop" };
    case "settling":
      return { kind: "send", enabled: false };
  }
}
