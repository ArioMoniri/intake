/**
 * Which palette the OS contrast request selects (INT-422,
 * docs/design/system-refresh.md §3). Pure, so the rule is node-testable; the
 * answer is gathered by lib/a11y/prefs.ts and applied in
 * components/Themed.tsx `useTheme()`.
 *
 * An OS that has not answered yet selects `standard`. This is the opposite
 * direction from the glass policy (lib/a11y/glass.ts, unknown is solid), and
 * it is safe for a measured reason: both palettes clear every floor in
 * theme.test.ts, so the standard palette never drops a patient below AA while
 * the OS is still answering, and an unknown-is-high rule would repaint every
 * patient's first frame.
 */
import type { Contrast } from "@/lib/theme";

export function contrastMode(increaseContrast: boolean | null): Contrast {
  return increaseContrast === true ? "high" : "standard";
}
