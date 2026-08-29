/**
 * INT-134 — tr labels for the taxonomy's visit types. Branch labels need no
 * helper: the branch's own `name_tr` IS the label (invariant 5). Visit types
 * are ids, so they get one message key each and this maps id → key.
 */
import type { MessageKey } from "../i18n";
import type { VisitTypeId } from "./branches";

const KEYS: Record<VisitTypeId, MessageKey> = {
  first: "visits.type.first",
  followup: "visits.type.followup",
  preop: "visits.type.preop",
  report: "visits.type.report",
  pregnancy_followup: "visits.type.pregnancy_followup",
  chronic_review: "visits.type.chronic_review",
  post_discharge: "visits.type.post_discharge",
  screening: "visits.type.screening",
  second_opinion: "visits.type.second_opinion",
  teleconsult: "visits.type.teleconsult",
};

export function visitTypeLabelKey(visitType: VisitTypeId): MessageKey {
  return KEYS[visitType];
}
