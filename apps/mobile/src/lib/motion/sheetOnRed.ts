/**
 * Whether a presented RED closes the section sheet (INT-338, MOTION-9;
 * docs/design/motion/motion-verification.md §1.1 C12 and U4, §1.3 System R2,
 * §3 S-6; ADR-033 §5, Proposed).
 *
 * It closes when, and only when, the RED is one the patient is shown: the
 * answer is the RED contract's own yield (./red `redFirstPaint`), keyed on
 * the presentation mode and never on "a RED event arrived". ALERT, CALM and
 * SILENT close it; DEFERRED_CLINICIAN closes nothing, so a finding meant for
 * the clinician alone makes no visible change on the patient's screen.
 *
 * This module is on the RED path, so e2e/motion.spec.ts pins it with the
 * other RED surface files and holds it to their scan: it reaches no
 * animation, haptic or navigation API. The close it decides carries no
 * motion either: ./transitions `sheetClose("red", …)` is instant.
 */
import type { RedPresentation } from "../livekit/red";
import { redFirstPaint, type RedContext } from "./red";

/** Whether the section sheet closes in the commit that presents `presentation`. */
export function closesSheetOnRed(presentation: RedPresentation, context: RedContext): boolean {
  return redFirstPaint(presentation, context).yields.closeModals;
}
