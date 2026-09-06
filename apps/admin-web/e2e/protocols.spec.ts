/**
 * INT-184 — Protocols module, console side (files/08 §148; files/09 §1-4).
 *
 * Acceptance, verbatim: *"branch x maturity matrix; approve/reject with 4-eyes;
 * clip coverage per voice"*.
 *
 * **What this runs against.** `e2e/fixtures/protocols.payload.json` is the
 * `GET /admin/protocols` composite, recorded from the real sources by
 * `scripts/dev/record_protocols_fixture.py` (the same "record, do not hand-mock"
 * discipline as models.spec.ts and compliance.spec.ts): the branch x maturity
 * matrix is `protocols.taxonomy.coverage` over the real taxonomy and pack tree,
 * the review queue's vocabulary is `intake_learning.proposals.PROPOSAL_TARGETS`
 * and its unmet checks are `intake_learning.evidence.REQUIRED_CHECKS`, and the
 * clip coverage is keyed by the real `VoiceProfile`. Asserting on the
 * presentation tree the renderer returns — not a DOM — matches the repo's node
 * lane (there is no browser runner; see models.spec.ts).
 *
 * **The negative controls.** Every property the acceptance and the invariants
 * turn on is paired with a near-miss the renderer must refuse: a branch that
 * resolves to an L0 pack rendered as coverage (invariant 13), an author's own
 * proposal rendered as approvable (invariant 4, four-eyes), a proposal whose
 * target is outside the proposal-only vocabulary (invariant 12), a candidate
 * flag carrying a level above YELLOW_REVIEW (invariant 1), and a clip row under
 * the `typed` profile (files/13 §13). Where the live surface is empty today
 * (the review queue has no persisted store), the near-miss rows are constructed
 * inline, exactly as compliance.spec.ts does for its emptyable surfaces.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import {
  ClipsUnderTypedProfile,
  ForbiddenProposalTarget,
  IncompleteEvidenceApprovable,
  InconsistentClipCounts,
  L0CountedAsCoverage,
  renderClipCoverage,
  renderCoverageMatrix,
  renderProtocolsModule,
  renderReviewQueue,
  SelfApprovalWouldBeRendered,
  type CoveragePayload,
  type ProtocolsPayload,
  type ReviewQueuePayload,
  type ReviewRow,
} from "../src/protocols/module";

const FIXTURES = join(__dirname, "fixtures");

function payload(): ProtocolsPayload {
  return JSON.parse(
    readFileSync(join(FIXTURES, "protocols.payload.json"), "utf8"),
  ) as ProtocolsPayload;
}

/** A well-formed review row: a rewording proposal on a real L0 pack slot, from
 * a distinct author, with a complete evidence bundle. Tests override one field
 * to build each near-miss — the same shape the queue would carry once the
 * proposal store lands (it is empty today). */
function reviewRow(overrides: Partial<ReviewRow> = {}): ReviewRow {
  return {
    proposal_id: "prop-0001",
    target: "QuestionWording",
    pack_id: "specialty.kardiyoloji",
    slot_id: "basvuru_nedeni",
    author: "svc:learning-pr-bot",
    candidate_flag_level: null,
    evidence_complete: true,
    unmet_checks: [],
    viewer_is_author: false,
    server_approvable: true,
    ...overrides,
  };
}

function queue(rows: readonly ReviewRow[]): ReviewQueuePayload {
  const live = payload().review_queue;
  return { ...live, rows };
}

describe("branch x maturity matrix", () => {
  it("paints one row per taxonomy branch, in taxonomy order", () => {
    const view = renderCoverageMatrix(payload().coverage);
    expect(view.rows.map((r) => r.branchId)).toEqual(
      payload().coverage.rows.map((r) => r.branch_id),
    );
    expect(view.rows.length).toBeGreaterThan(0);
  });

  it("carries branch, name_tr, cluster, status and the draft maturity as text", () => {
    const view = renderCoverageMatrix(payload().coverage);
    const kardiyoloji = view.rows.find((r) => r.branchId === "kardiyoloji");
    expect(kardiyoloji).toBeDefined();
    expect(kardiyoloji!.nameTr).toEqual("Kardiyoloji");
    expect(kardiyoloji!.cluster).toEqual("medical");
    expect(kardiyoloji!.status).toEqual("MISSING");
    // branch x *maturity*: the draft that exists is named, at its level, and it
    // is not counted as coverage (files/09 §2)
    expect(kardiyoloji!.maturityLabel).toContain("L0");
    expect(kardiyoloji!.servable).toBe(false);
  });

  it("summarises coverage by status and shows no branch resolves to L1+ today", () => {
    const view = renderCoverageMatrix(payload().coverage);
    expect(view.summary.missing).toBeGreaterThan(0);
    // the honest current state: every intake branch is a gap (invariant 13's
    // matrix exists to surface exactly this), Acil Tıp is excluded
    expect(view.summary.direct + view.summary.cluster).toBe(0);
    expect(view.summary.excluded).toBeGreaterThan(0);
  });

  it("marks Acil Tıp EXCLUDED — RED routing only, never a served pack", () => {
    const view = renderCoverageMatrix(payload().coverage);
    const excluded = view.rows.filter((r) => r.status === "EXCLUDED");
    expect(excluded.length).toBeGreaterThan(0);
    for (const row of excluded) {
      expect(row.servable).toBe(false);
      expect(row.servedPackId).toBeNull();
      expect(row.note.length).toBeGreaterThan(0);
    }
  });

  it("refuses to render an L0 pack as coverage (invariant 13)", () => {
    // near-miss: a stale or tampered body claims a branch resolves DIRECT while
    // the pack that would serve is L0 — the L0PackServedError contradiction
    const live = payload().coverage;
    const tampered: CoveragePayload = {
      ...live,
      rows: [
        {
          ...live.rows[0]!,
          status: "DIRECT",
          served_pack_id: "specialty.x",
          served_maturity: "L0",
        },
      ],
    };
    expect(() => renderCoverageMatrix(tampered)).toThrow(L0CountedAsCoverage);
  });

  it("refuses a MISSING row that nonetheless names a served pack", () => {
    const live = payload().coverage;
    const tampered: CoveragePayload = {
      ...live,
      rows: [{ ...live.rows[0]!, status: "MISSING", served_pack_id: "specialty.x" }],
    };
    expect(() => renderCoverageMatrix(tampered)).toThrow(L0CountedAsCoverage);
  });
});

describe("approve/reject with 4-eyes", () => {
  it("the live queue is empty today, with the real vocabulary and checks shown", () => {
    const view = renderReviewQueue(payload().review_queue);
    // no persisted proposal store: the PR-bot opens PRs, a CODEOWNER approves
    expect(view.rows).toEqual([]);
    expect(view.allowedTargets).toContain("QuestionWording");
    expect(view.allowedTargets).toContain("CandidateRedFlag");
    expect(view.unmetCheckNames.length).toBeGreaterThan(0);
  });

  it("gates approve on a complete evidence bundle; reject stays open to a reviewer", () => {
    const view = renderReviewQueue(
      queue([
        reviewRow({
          evidence_complete: false,
          unmet_checks: ["simulator_run"],
          server_approvable: false,
        }),
      ]),
    );
    const row = view.rows[0]!;
    expect(row.approveControl.enabled).toBe(false);
    expect(row.approveControl.disabledReason).toContain("evidence");
    // an incomplete proposal can still be rejected by the second person
    expect(row.rejectControl.enabled).toBe(true);
  });

  it("enables approve only for a distinct reviewer on a complete bundle", () => {
    const view = renderReviewQueue(queue([reviewRow()]));
    const row = view.rows[0]!;
    expect(row.approveControl.enabled).toBe(true);
    expect(row.rejectControl.enabled).toBe(true);
  });

  it("four-eyes: an author may neither approve nor reject their own proposal", () => {
    const view = renderReviewQueue(
      queue([reviewRow({ viewer_is_author: true, server_approvable: false })]),
    );
    const row = view.rows[0]!;
    expect(row.approveControl.enabled).toBe(false);
    expect(row.approveControl.disabledReason).toMatch(/four.eyes|author/i);
    expect(row.rejectControl.enabled).toBe(false);
  });

  it("refuses a payload asserting the author is approvable (four-eyes, invariant 4)", () => {
    expect(() =>
      renderReviewQueue(queue([reviewRow({ viewer_is_author: true, server_approvable: true })])),
    ).toThrow(SelfApprovalWouldBeRendered);
  });

  it("refuses an approvable proposal whose evidence bundle is incomplete (files/09 §4)", () => {
    expect(() =>
      renderReviewQueue(
        queue([reviewRow({ evidence_complete: false, unmet_checks: ["simulator_run"] })]),
      ),
    ).toThrow(IncompleteEvidenceApprovable);
  });

  it("refuses a proposal outside the proposal-only vocabulary (invariant 12)", () => {
    // the console approves/rejects PROPOSALS; a red-flag-level change is not one
    expect(() => renderReviewQueue(queue([reviewRow({ target: "RedFlagLevelChange" })]))).toThrow(
      ForbiddenProposalTarget,
    );
  });

  it("refuses a candidate red flag carrying a level above YELLOW_REVIEW (invariant 1)", () => {
    expect(() =>
      renderReviewQueue(
        queue([reviewRow({ target: "CandidateRedFlag", candidate_flag_level: "RED" })]),
      ),
    ).toThrow(ForbiddenProposalTarget);
    // the permitted candidate level renders
    const view = renderReviewQueue(
      queue([reviewRow({ target: "CandidateRedFlag", candidate_flag_level: "YELLOW_REVIEW" })]),
    );
    expect(view.rows[0]!.target).toEqual("CandidateRedFlag");
  });
});

describe("clip coverage per voice", () => {
  it("paints one row per spoken voice, none under the typed profile", () => {
    const view = renderClipCoverage(payload().clip_coverage);
    expect(view.voices.length).toBeGreaterThan(0);
    expect(view.voices.some((v) => v.profile === "typed")).toBe(false);
    expect(view.voices.map((v) => v.profile)).toContain("residency_tr");
  });

  it("shows counts as non-grouped atoms and explains the empty state (inv 22)", () => {
    const view = renderClipCoverage(payload().clip_coverage);
    const voice = view.voices[0]!;
    for (const cell of voice.cells) {
      // a count is rendered without a grouping separator a reader could misread
      expect(cell.value).not.toMatch(/[,  ]/);
    }
    expect(view.servablePackCount).toBe(0);
    expect(view.note.length).toBeGreaterThan(0);
  });

  it("refuses a clip row under the typed profile (files/13 §13)", () => {
    const live = payload().clip_coverage;
    const tampered = {
      ...live,
      voices: [{ ...live.voices[0]!, profile: "typed" }],
    };
    expect(() => renderClipCoverage(tampered)).toThrow(ClipsUnderTypedProfile);
  });

  it("refuses inconsistent counts (missing must be required minus cached)", () => {
    const live = payload().clip_coverage;
    const tampered = {
      ...live,
      voices: [{ ...live.voices[0]!, required: 10, cached: 3, missing: 2 }],
    };
    expect(() => renderClipCoverage(tampered)).toThrow(InconsistentClipCounts);
  });
});

describe("the whole module composes", () => {
  it("renders every surface from the recorded composite", () => {
    const view = renderProtocolsModule(payload());
    expect(view.matrix.rows.length).toBeGreaterThan(0);
    expect(Array.isArray(view.reviewQueue.rows)).toBe(true);
    expect(view.clipCoverage.voices.length).toBeGreaterThan(0);
  });
});
