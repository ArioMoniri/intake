/**
 * When the typed lane shows its "kendi sözlerinizle" invitation
 * (`intake.open.hint`): once per session, at the first open question the
 * patient meets (INT-371, int-demo 20aca9e2).
 *
 * Shown under every open question, the same sentence read as noise, and the
 * spoken lane dropped its per-turn invitation for the same reason
 * (dialogue/speech.ts). A later open step is not left unexplained: its answer
 * field carries the same text as its accessibility hint, and
 * `intake.open.orChoose` sits under it.
 *
 * The invitation is pinned to a question rather than to step one. A
 * voice→typed hand-off resumes at the first UNanswered step, which can be any
 * step, and the invitation follows the patient there. Pure, so the rule is
 * tested on data; StepFlow holds the anchor in state.
 */

/**
 * The question the invitation is pinned to for this session: `anchor` once
 * it is set, else the current question if it is open, else still none.
 */
export function openHintAnchor(
  anchor: string | null,
  questionId: string,
  open: boolean,
): string | null {
  if (anchor !== null) {
    return anchor;
  }
  return open ? questionId : null;
}

/** Whether this step shows the invitation: only the anchored open question. */
export function showsOpenHint(anchor: string | null, questionId: string, open: boolean): boolean {
  return open && openHintAnchor(anchor, questionId, open) === questionId;
}
