/**
 * Bugün's one focus (INT-594; 02 §5.1): the next visit and its single most
 * useful action, derived from the note's real state.
 *
 * The state is `effectiveStatus`, the rule the visit detail already uses. It
 * combines the visit's own ladder step, the draft on this phone, and the note
 * outbox's verdict: a sent note counts as sent only once the server has
 * confirmed it (INT-587). The feed's `noteStatus` alone cannot be the state.
 * A hospital-feed visit always carries null there (api.ts `syncVisits`), and
 * reading it raw kept build 7 on "prepare" whatever the patient had done.
 *
 * Which visits: only upcoming ones, by the rule Vizitlerim uses (`splitVisits`:
 * dated today or later, or dateless). The screen labels the focus "Sıradaki
 * vizit", and a past visit is never next (legal review of #1013). The soonest
 * dated visit comes first, then the dateless ones, whatever order the feed
 * sent.
 *
 * Order: a visit that still needs preparing comes first, because that is the
 * action. When none is left, the next visit whose note the server confirmed is
 * shown as sent, so Bugün never says there is no visit while one is coming.
 */
import { effectiveStatus, type NoteState } from "./intake/note";
import type { VisitFixture } from "./types/account";
import { splitVisits } from "./visits";

/** Soonest dated visit first, dateless ones after; ties keep the feed's order. */
function soonestFirst(a: VisitFixture, b: VisitFixture): number {
  if (a.date === b.date) {
    return 0;
  }
  if (a.date === null) {
    return 1;
  }
  if (b.date === null) {
    return -1;
  }
  return a.date < b.date ? -1 : 1;
}

export type TodayFocus =
  | { kind: "prepare"; visit: VisitFixture; status: null; cta: "visit.prepare" }
  | { kind: "continue"; visit: VisitFixture; status: "draft"; cta: "today.continueCta" }
  | { kind: "sent"; visit: VisitFixture; status: "sent"; cta: "today.openCta" }
  | { kind: "none" };

export function todayFocus(
  visits: readonly VisitFixture[],
  notes: Readonly<Record<string, NoteState | undefined>>,
  isDelivered: (visitId: string) => boolean,
  todayIso: string,
): TodayFocus {
  const upcoming = [...splitVisits(visits, todayIso).upcoming].sort(soonestFirst);
  const rows = upcoming.map((visit) => ({
    visit,
    status: effectiveStatus(visit.noteStatus, notes[visit.id], isDelivered(visit.id)),
  }));
  for (const { visit, status } of rows) {
    if (status === null) {
      return { kind: "prepare", visit, status, cta: "visit.prepare" };
    }
    if (status === "draft") {
      return { kind: "continue", visit, status, cta: "today.continueCta" };
    }
  }
  const sent = rows.find((row) => row.status === "sent");
  return sent === undefined
    ? { kind: "none" }
    : { kind: "sent", visit: sent.visit, status: "sent", cta: "today.openCta" };
}
