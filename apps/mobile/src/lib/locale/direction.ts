/**
 * INT-301 / INT-346 — the writing direction of the locales this build ships.
 *
 * Every locale this build can offer is written left-to-right: `tr`, and `en`
 * as the reviewer's mirror of it. Right-to-left layout is deferred to INT-253's
 * P3 audit (owner decision, 2026-09-26). INT-301 had derived a direction from
 * each locale's script and applied it to the shared screen anatomy; that
 * reached the tree ahead of the audit and has been removed, so there is one
 * direction here and no locale-dependent branch.
 *
 * When the audit lands, it decides how a right-to-left locale is laid out.
 * Until then the chooser reports this single direction for every choice, and
 * nothing in the render tree sets one (React Native's default is
 * left-to-right).
 */

/** The only writing direction this build lays out. */
export type TextDirection = "ltr";

/** The writing direction of every locale this build offers. */
export const TEXT_DIRECTION: TextDirection = "ltr";
