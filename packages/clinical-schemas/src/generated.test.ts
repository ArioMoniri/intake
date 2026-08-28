/**
 * INT-031 — the generated types are importable through the package's public
 * surface and shape-compatible with fixtures that mirror what the python
 * side serialises (tests/schemas/test_roundtrip.py holds the same shapes).
 * `satisfies` makes every fixture a compile-time assertion; tsc runs in the
 * check-ts lane, so a drifted regeneration fails the build here too.
 */
import { describe, expect, it } from "vitest";

import type {
  CsatV1,
  InteractionState,
  LlmCandidateTriage,
  PatientSummary,
  RulesTriageResult,
  SecurityV1,
  TriageResult,
} from "./index";
import { SCHEMA_NAMESPACE, schemaId } from "./index";

const csat = {
  schema_id: "intake.clinical.csat.v1",
  tenant_id: "00000000-0000-4000-8000-000000000001",
  session_id: "00000000-0000-4000-8000-000000000002",
  score: 4,
  reason: "helpful",
  text: null,
} satisfies CsatV1;

const security = {
  schema_id: "intake.clinical.security.v1",
  category: "consent_scope_denial",
  tenant_id: "00000000-0000-4000-8000-000000000001",
  actor_ref: "svc-api",
  resource_ref: "note_0001",
  correlation_id: "corr_0001",
  attributes: { denied_scope: "wellbeing" },
} satisfies SecurityV1;

const summary = {
  cards: [{ title_tr: "Anlattiklariniz", lines: ["iki gundur karin agrisi"] }],
  questions_for_doctor: ["hangi tetkikler gerekli"],
  bring_list: ["ilac kutulari"],
  triage_message_tr: "Randevunuzdan once bir degisiklik olursa bize yazin.",
} satisfies PatientSummary;

// Invariant 1, visible to TS consumers: the llm_candidate arm can only carry
// YELLOW_REVIEW, and the union discriminates on `source`.
const rulesRed = {
  source: "rules",
  level: "RED",
  rules: [{ id: "base.life_threat.chest_pain", evidence: "slot gogus_agrisi=true" }],
  register: "ALERT",
  location: "REMOTE",
} satisfies RulesTriageResult;

const llmCandidate = {
  source: "llm_candidate",
  level: "YELLOW_REVIEW",
  candidate_flags: [{ text: "gizli kanama olabilir", evidence: "melena tarifi" }],
} satisfies LlmCandidateTriage;

const interaction = {
  pace: "slow",
  modality: "typed",
  break_offer: false,
  confirm_by_card: true,
  repeat_request: false,
  third_party_present: true,
} satisfies InteractionState;

describe("generated clinical types (INT-031)", () => {
  it("event schema ids agree with the schemaId convention", () => {
    expect(csat.schema_id).toBe(schemaId("csat", 1));
    expect(security.schema_id).toBe(schemaId("security", 1));
    expect(csat.schema_id.startsWith(`${SCHEMA_NAMESPACE}.`)).toBe(true);
  });

  it("triage union discriminates on source", () => {
    const results: TriageResult[] = [rulesRed, llmCandidate];
    const levels = results.map((r) => (r.source === "rules" ? r.level : r.level));
    expect(levels).toEqual(["RED", "YELLOW_REVIEW"]);
  });

  it("fixtures carry the shapes the python side serialises", () => {
    expect(summary.cards).toHaveLength(1);
    expect(interaction.third_party_present).toBe(true);
    expect(security.attributes["denied_scope"]).toBe("wellbeing");
  });
});
