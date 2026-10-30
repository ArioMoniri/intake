/**
 * Protocols module — the console side (INT-184; files/08 §148; files/09 §1-4).
 *
 * Like the models and compliance modules, this turns the `GET /admin/protocols`
 * composite into exactly what the page paints and decides nothing the server did
 * not already decide. What it adds is a set of refusals that mirror the server's
 * invariants, so a stale tab, a cached response or a tampered body cannot buy
 * the page a property the server would never have served:
 *
 * - **An L0 pack cannot be painted as coverage** (`L0CountedAsCoverage`). The
 *   branch × maturity matrix is `protocols.taxonomy.coverage`; invariant 13 says
 *   every branch resolves to an L1+ pack or its cluster pack, and an L0 pack
 *   resolved for a live session raises (`L0PackServedError`). A row that claims
 *   to resolve (DIRECT/CLUSTER) while the pack behind it is L0 — or a row that
 *   claims not to resolve (MISSING/EXCLUDED) while naming a served pack — is the
 *   contradiction the matrix exists to make impossible, so it is refused.
 *
 * - **An author's own proposal cannot be painted as approvable**
 *   (`SelfApprovalWouldBeRendered`). Approval is a two-person act (four-eyes,
 *   files/08 §2.1; invariant 4). The server carries its own approvable verdict
 *   *and* whether the viewer is the author; when they contradict, the row is
 *   refused rather than rendered with a live approve button the author could
 *   press.
 *
 * - **An incomplete proposal cannot be painted as approvable**
 *   (`IncompleteEvidenceApprovable`). files/09 §4 requires an evidence bundle;
 *   a bundle with an unmet check cannot open a PR, so it cannot be approvable.
 *
 * - **A change outside the proposal-only vocabulary cannot be painted**
 *   (`ForbiddenProposalTarget`). Invariant 12: learning is proposal-only, and
 *   this console approves/rejects PROPOSALS — it never itself edits a red-flag
 *   level, an instrument, a consent text, a Talker tool or routing (those flow
 *   through the PR + CODEOWNER path). A target outside
 *   `intake_learning.proposals.PROPOSAL_TARGETS`, or a candidate red flag
 *   carrying a level above `YELLOW_REVIEW` (invariant 1), is refused.
 *
 * - **A clip cannot be painted under the `typed` profile**
 *   (`ClipsUnderTypedProfile`, `InconsistentClipCounts`). `typed` carries no
 *   clips ever (files/13 §13), and a voice's counts must be internally
 *   consistent (missing = required − cached).
 *
 * The whole module is a pure projection: it reads the recorded payload and
 * returns the presentation tree. It performs no mutation and opens no socket —
 * approve/reject flows through the INT-180 admin shell's audited, four-eyes
 * routes, which this file never re-implements.
 */

/* ------------------------------------------------------------------ */
/* Wire contract — the recorded shape of GET /admin/protocols          */
/* ------------------------------------------------------------------ */

export type ResolutionStatus = "DIRECT" | "CLUSTER" | "MISSING" | "EXCLUDED";

export interface CoverageRow {
  readonly branch_id: string;
  readonly name_tr: string;
  readonly cluster: string;
  readonly status: ResolutionStatus;
  /** The servable pack, present only for DIRECT/CLUSTER. */
  readonly served_pack_id: string | null;
  /** The servable pack's maturity (L1+ by construction), else null. */
  readonly served_maturity: string | null;
  /** The L0 draft named but never counted as coverage (files/09 §2). */
  readonly draft_pack_id: string | null;
  readonly draft_maturity: string | null;
  readonly note: string;
}

export interface CoverageSummary {
  readonly total: number;
  readonly direct: number;
  readonly cluster: number;
  readonly missing: number;
  readonly excluded: number;
}

export interface CoveragePayload {
  readonly generated_at: string;
  readonly taxonomy_source: string;
  readonly pack_count: number;
  readonly summary: CoverageSummary;
  readonly rows: readonly CoverageRow[];
}

export interface ReviewRow {
  readonly proposal_id: string;
  /** A member of `PROPOSAL_TARGETS` (files/09 §4) — the closed vocabulary. */
  readonly target: string;
  readonly pack_id: string;
  readonly slot_id: string;
  readonly author: string;
  /** Only a CandidateRedFlag carries one, and only `YELLOW_REVIEW` (inv 1). */
  readonly candidate_flag_level: string | null;
  readonly evidence_complete: boolean;
  readonly unmet_checks: readonly string[];
  /** Server-computed: is the viewer the author of this proposal? */
  readonly viewer_is_author: boolean;
  /** The server's own four-eyes + evidence verdict for this viewer. */
  readonly server_approvable: boolean;
}

export interface ReviewQueuePayload {
  readonly source: string;
  readonly allowed_targets: readonly string[];
  readonly unmet_check_names: readonly string[];
  readonly rows: readonly ReviewRow[];
}

export interface MissingClip {
  readonly clip_id: string;
  readonly pack_id: string;
}

export interface ClipVoice {
  readonly voice_id: string;
  readonly profile: string;
  readonly role: string;
  readonly required: number;
  readonly cached: number;
  readonly missing: number;
  readonly missing_clips: readonly MissingClip[];
}

export interface ClipCoveragePayload {
  readonly generated_at: string;
  readonly servable_pack_count: number;
  readonly note: string;
  readonly voices: readonly ClipVoice[];
}

export interface ProtocolsPayload {
  readonly coverage: CoveragePayload;
  readonly review_queue: ReviewQueuePayload;
  readonly clip_coverage: ClipCoveragePayload;
}

/* ------------------------------------------------------------------ */
/* Presentation tree — what the page paints                            */
/* ------------------------------------------------------------------ */

export interface Cell {
  readonly label: string;
  readonly value: string;
}

/** A control the reader may operate — dead while a gate stands, with a reason. */
export interface Control {
  readonly enabled: boolean;
  readonly disabledReason: string | null;
}

export interface MatrixRow {
  readonly branchId: string;
  readonly nameTr: string;
  readonly cluster: string;
  readonly status: ResolutionStatus;
  /** True exactly for a branch that resolves to an L1+ pack (DIRECT/CLUSTER). */
  readonly servable: boolean;
  readonly servedPackId: string | null;
  /** Readable maturity: "L0 draft — not served", "L1 (served)", "excluded". */
  readonly maturityLabel: string;
  /** The served pack's maturity (L1+), else null — for a page that words it itself. */
  readonly servedMaturity: string | null;
  /** The L0 draft's maturity, named and never counted as coverage. */
  readonly draftMaturity: string | null;
  readonly note: string;
}

export interface MatrixPresentation {
  readonly summary: CoverageSummary;
  readonly rows: readonly MatrixRow[];
}

export interface ReviewRowPresentation {
  readonly proposalId: string;
  readonly target: string;
  readonly packId: string;
  readonly slotId: string;
  readonly author: string;
  readonly evidenceComplete: boolean;
  readonly unmetChecks: readonly string[];
  readonly approveControl: Control;
  readonly rejectControl: Control;
}

export interface ReviewQueuePresentation {
  readonly source: string;
  readonly allowedTargets: readonly string[];
  readonly unmetCheckNames: readonly string[];
  readonly rows: readonly ReviewRowPresentation[];
}

export interface ClipVoicePresentation {
  readonly voiceId: string;
  readonly profile: string;
  readonly role: string;
  readonly cells: readonly Cell[];
  readonly missingClips: readonly string[];
}

export interface ClipCoveragePresentation {
  readonly servablePackCount: number;
  readonly note: string;
  readonly voices: readonly ClipVoicePresentation[];
}

export interface ProtocolsPresentation {
  readonly matrix: MatrixPresentation;
  readonly reviewQueue: ReviewQueuePresentation;
  readonly clipCoverage: ClipCoveragePresentation;
}

/* ------------------------------------------------------------------ */
/* Refusals — the properties a stale or tampered payload cannot buy    */
/* ------------------------------------------------------------------ */

/** A coverage row whose status and pack maturity contradict (invariant 13). */
export class L0CountedAsCoverage extends Error {
  constructor(branchId: string, detail: string) {
    super(
      `refusing to render branch '${branchId}': ${detail}. Every branch resolves to an ` +
        `L1+ pack or its cluster pack, and an L0 pack resolved for a live session raises ` +
        `(CLAUDE.md invariant 13; protocols.taxonomy.L0PackServedError)`,
    );
    this.name = "L0CountedAsCoverage";
  }
}

/** A proposal outside the proposal-only vocabulary (invariant 12, invariant 1). */
export class ForbiddenProposalTarget extends Error {
  constructor(detail: string) {
    super(
      `refusing to render this review row: ${detail}. This console approves/rejects ` +
        `PROPOSALS; it never edits a red-flag level, instrument, consent text, Talker tool ` +
        `or routing — those flow through the PR + CODEOWNER path (CLAUDE.md invariant 12)`,
    );
    this.name = "ForbiddenProposalTarget";
  }
}

/** An author's own proposal asserted approvable (four-eyes, invariant 4). */
export class SelfApprovalWouldBeRendered extends Error {
  constructor(proposalId: string) {
    super(
      `refusing to render proposal '${proposalId}' as approvable while the viewer is its ` +
        `author: approval is a two-person act (files/08 §2.1; CLAUDE.md invariant 4). A stale ` +
        `or tampered body must not buy the author a live approve control`,
    );
    this.name = "SelfApprovalWouldBeRendered";
  }
}

/** An incomplete proposal asserted approvable (files/09 §4). */
export class IncompleteEvidenceApprovable extends Error {
  constructor(proposalId: string, unmet: readonly string[]) {
    super(
      `refusing to render proposal '${proposalId}' as approvable while its evidence bundle ` +
        `is incomplete (unmet: ${unmet.join(", ") || "unknown"}): files/09 §4 requires a ` +
        `complete bundle, and a bundle with an unmet check cannot open a PR`,
    );
    this.name = "IncompleteEvidenceApprovable";
  }
}

/** A clip rendered under the `typed` profile (files/13 §13). */
export class ClipsUnderTypedProfile extends Error {
  constructor(voiceId: string) {
    super(
      `refusing to render clip coverage for voice '${voiceId}' under the 'typed' profile: ` +
        `typed means text only — no clip, no speech_tr, ever (files/13 §13)`,
    );
    this.name = "ClipsUnderTypedProfile";
  }
}

/** A clip voice whose counts do not add up (missing = required − cached). */
export class InconsistentClipCounts extends Error {
  constructor(voiceId: string) {
    super(
      `refusing to render clip coverage for voice '${voiceId}': its counts do not reconcile ` +
        `(missing must equal required − cached), so the body is stale or tampered`,
    );
    this.name = "InconsistentClipCounts";
  }
}

/* ------------------------------------------------------------------ */
/* Renderers                                                           */
/* ------------------------------------------------------------------ */

/** A count crosses the boundary as one atom, no grouping separator (inv 22). */
function count(value: number): string {
  return value.toLocaleString("en-GB", { useGrouping: false });
}

function renderMatrixRow(row: CoverageRow): MatrixRow {
  const servable = row.status === "DIRECT" || row.status === "CLUSTER";
  if (servable) {
    // a resolving row must name a servable pack at L1+, never L0 or nothing
    if (row.served_pack_id === null) {
      throw new L0CountedAsCoverage(row.branch_id, `status ${row.status} names no served pack`);
    }
    if (row.served_maturity === null || row.served_maturity === "L0") {
      throw new L0CountedAsCoverage(
        row.branch_id,
        `status ${row.status} resolves to a pack whose maturity is ${row.served_maturity ?? "unknown"}`,
      );
    }
  } else if (row.served_pack_id !== null) {
    // a non-resolving row must not name a served pack
    throw new L0CountedAsCoverage(
      row.branch_id,
      `status ${row.status} names served pack '${row.served_pack_id}'`,
    );
  }

  let maturityLabel: string;
  if (servable) {
    maturityLabel = `${row.served_maturity} (served)`;
  } else if (row.status === "EXCLUDED") {
    maturityLabel = "excluded — no intake pack";
  } else if (row.draft_maturity !== null) {
    maturityLabel = `${row.draft_maturity} draft — not served`;
  } else {
    maturityLabel = "no pack";
  }

  return {
    branchId: row.branch_id,
    nameTr: row.name_tr,
    cluster: row.cluster,
    status: row.status,
    servable,
    servedPackId: row.served_pack_id,
    maturityLabel,
    servedMaturity: servable ? row.served_maturity : null,
    draftMaturity: row.draft_maturity,
    note: row.note,
  };
}

/** Build the branch × maturity matrix, refusing any L0-as-coverage row. */
export function renderCoverageMatrix(payload: CoveragePayload): MatrixPresentation {
  return {
    summary: payload.summary,
    rows: payload.rows.map(renderMatrixRow),
  };
}

function renderReviewRow(row: ReviewRow, allowedTargets: readonly string[]): ReviewRowPresentation {
  if (!allowedTargets.includes(row.target)) {
    throw new ForbiddenProposalTarget(
      `target '${row.target}' is not one of the allowed proposal types (${allowedTargets.join(", ")})`,
    );
  }
  if (row.candidate_flag_level !== null && row.candidate_flag_level !== "YELLOW_REVIEW") {
    throw new ForbiddenProposalTarget(
      `a candidate red flag enters as YELLOW_REVIEW only; '${row.candidate_flag_level}' is above ` +
        `the cap an LLM-derived flag may carry (CLAUDE.md invariant 1)`,
    );
  }
  if (row.server_approvable && row.viewer_is_author) {
    throw new SelfApprovalWouldBeRendered(row.proposal_id);
  }
  if (row.server_approvable && !row.evidence_complete) {
    throw new IncompleteEvidenceApprovable(row.proposal_id, row.unmet_checks);
  }

  const approveDisabledReason = row.viewer_is_author
    ? "four-eyes: an author may not approve their own proposal (files/08 §2.1)"
    : !row.evidence_complete
      ? `evidence bundle incomplete — unmet: ${row.unmet_checks.join(", ") || "unknown"} (files/09 §4)`
      : "not approvable in this state";

  return {
    proposalId: row.proposal_id,
    target: row.target,
    packId: row.pack_id,
    slotId: row.slot_id,
    author: row.author,
    evidenceComplete: row.evidence_complete,
    unmetChecks: row.unmet_checks,
    approveControl: {
      enabled: row.server_approvable,
      disabledReason: row.server_approvable ? null : approveDisabledReason,
    },
    rejectControl: {
      // a reviewer who is not the author may reject at any maturity; the author
      // may not reject their own proposal either (four-eyes cuts both ways)
      enabled: !row.viewer_is_author,
      disabledReason: row.viewer_is_author
        ? "four-eyes: an author may not reject their own proposal (files/08 §2.1)"
        : null,
    },
  };
}

/** Build the review queue, refusing any row that breaks four-eyes or scope. */
export function renderReviewQueue(payload: ReviewQueuePayload): ReviewQueuePresentation {
  return {
    source: payload.source,
    allowedTargets: payload.allowed_targets,
    unmetCheckNames: payload.unmet_check_names,
    rows: payload.rows.map((row) => renderReviewRow(row, payload.allowed_targets)),
  };
}

function renderClipVoice(voice: ClipVoice): ClipVoicePresentation {
  if (voice.profile === "typed") {
    throw new ClipsUnderTypedProfile(voice.voice_id);
  }
  if (voice.missing !== voice.required - voice.cached) {
    throw new InconsistentClipCounts(voice.voice_id);
  }
  return {
    voiceId: voice.voice_id,
    profile: voice.profile,
    role: voice.role,
    cells: [
      { label: "required", value: count(voice.required) },
      { label: "cached", value: count(voice.cached) },
      { label: "missing", value: count(voice.missing) },
    ],
    missingClips: voice.missing_clips.map((clip) => clip.clip_id),
  };
}

/** Build clip coverage per voice, refusing a typed row or inconsistent counts. */
export function renderClipCoverage(payload: ClipCoveragePayload): ClipCoveragePresentation {
  return {
    servablePackCount: payload.servable_pack_count,
    note: payload.note,
    voices: payload.voices.map(renderClipVoice),
  };
}

/**
 * Build the whole module from the recorded composite.
 *
 * A refusal in any surface propagates: a protocols console that painted an L0
 * pack as coverage, an author approving their own proposal, or a clip under the
 * typed profile would be worse than no console, so the page does not render
 * past one.
 */
export function renderProtocolsModule(payload: ProtocolsPayload): ProtocolsPresentation {
  return {
    matrix: renderCoverageMatrix(payload.coverage),
    reviewQueue: renderReviewQueue(payload.review_queue),
    clipCoverage: renderClipCoverage(payload.clip_coverage),
  };
}
