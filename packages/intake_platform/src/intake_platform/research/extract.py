"""INT-230 — the research export gate: consent, ethics id, exclusion, k.

**This produces pseudonymisation, not anonymisation, and the code says so.**
KSVY m.16(1) permits scientific work on health data *anonim hâle getirilen* —
anonymised by the controller — under KVKK m.28/1(b). What this pipeline can
actually produce is a keyed HMAC pseudonym over a closed vocabulary:
re-derivable by whoever holds the tokenization key, therefore personal data,
therefore **not** m.16(1)'s route. files/06 §75 states the alternative in the
same sentence — *"All research consented (`research`) or anonymised per
KSVY-16; ethics IDs recorded on every export"* — and this gate takes the
consent route: the `research` scope on the ledger, plus a registered study
with a live ethics approval. Whether KSVY m.16(2)'s separate limb (scientific
processing under KVKK m.28/1(c)) would additionally apply is a question for
counsel and is not asserted anywhere in this package.

**Six gates, each failing closed, in a fixed order.**

1. ``k`` is supplied by the caller with no default and may not go below
   :data:`~intake_platform.analytics.K_ANONYMITY_FLOOR`. The floor is
   imported, never restated: two copies of a privacy threshold are two
   chances for one of them to drift down (the INT-171/INT-240 rule).
2. The study resolves in the registry **on the date being asked about**, with
   no grace day past ``approval_valid_until`` (files/10 §9, invariant 35).
3. The recipient is on that study's closed list.
4. ``research_extracts`` carries a stated retention. files/06 §3 says "per
   ethics protocol" and no protocol exists, so the shipped row is
   ``draft_needs_source`` and this gate refuses: data whose destruction date
   nobody can state may not be created (KVKK m.7, DEST-2017).
5. Every value is admitted by the spec's **closed vocabulary**, and refused
   additionally if the pattern tier finds an identifier in it — the rules live
   in :mod:`intake_platform.research.values`, which records why acceptance can
   only ever come from the vocabulary.
6. The consent filter runs through the ONE evaluator
   (:func:`intake_platform.consent.consent_state`), and a patient who has not
   granted `research` is **dropped**, not flagged: no row, no marker, no
   count of the dropped. Then the quasi-identifier cross-tab goes through
   :func:`intake_platform.analytics.materialise`, which refuses the whole
   artefact rather than suppressing a cell — a reader holding every cell but
   one recovers it by subtraction.

**What is not here.** No narrative of any kind, redacted or otherwise. No
order statistic: a min or a max is one real patient's value at any cohort
size, so such a measure cannot be declared at all. No histogram of an
observed value: a scrape after a single observation leaks it through ``_sum``
over ``_count``, so the only thing this module meters is refusals and serves,
labelled with a spec name and a reason class.
"""

from __future__ import annotations

import hashlib
import uuid
from collections import defaultdict
from collections.abc import Callable, Sequence
from datetime import UTC, datetime

from prometheus_client import Counter
from sqlalchemy.ext.asyncio import AsyncSession

from intake_platform.analytics import (
    K_ANONYMITY_FLOOR,
    Cell,
    Cohort,
    KAnonymityRefusal,
    Measurement,
    ThresholdBelowFloor,
    materialise,
)
from intake_platform.consent import ConsentTextCatalog, consent_state
from intake_platform.consent.service import ConsentAudit
from intake_platform.research.artefact import (
    PseudonymisedExtract,
    PseudonymisedRow,
    SubjectRow,
    canonical_bytes,
)
from intake_platform.research.register import ExtractRecord, ExtractRegister
from intake_platform.research.studies import (
    StudyApprovalLapsedError,
    StudyApprovalNotYetInForceError,
    StudyRecord,
    StudyRegistry,
    StudyRegistryRefusal,
)
from intake_platform.research.values import (
    RESEARCH_SCOPE,
    ResearchExportRefused,
    ResearchExtractSpec,
    ResearchRefusalReason,
    check_export_field,
    check_export_value,
)
from intake_platform.retention import DestroyableClass, RetentionKind, RetentionPolicy
from intake_platform.retention.policy import ClassStatus
from intake_platform.tokenization import Tokenizer

__all__ = [
    "RESEARCH_EXTRACT_REFUSED",
    "RESEARCH_EXTRACT_SERVED",
    "ResearchExportGate",
]

RESEARCH_EXTRACT_REFUSED = Counter(
    "research_extract_refused_total",
    "Research export requests refused, by extract spec and reason class. "
    "Labels carry no study cohort, no count and no dimension value (inv. 6).",
    ["spec", "reason"],
)

RESEARCH_EXTRACT_SERVED = Counter(
    "research_extract_served_total",
    "Research extracts served, by extract spec. A count of extracts, never of subjects.",
    ["spec"],
)


class ResearchExportGate:
    """The one path from clinical data to a research extract.

    Everything the gate needs is supplied at construction and none of it has a
    default: the registry that says which studies exist, the retention policy
    that says whether an extract may be created at all, the tokenizer that
    derives the study-scoped pseudonym, the register the extract is recorded
    in, the audit chain the attempt is recorded in, and the consent-text
    catalog the ledger is evaluated against.
    """

    def __init__(
        self,
        *,
        registry: StudyRegistry,
        retention: RetentionPolicy,
        tokenizer: Tokenizer,
        register: ExtractRegister,
        audit: ConsentAudit,
        catalog: ConsentTextCatalog,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._registry = registry
        self._retention = retention
        self._tokenizer = tokenizer
        self._register = register
        self._audit = audit
        self._catalog = catalog
        self._clock = clock if clock is not None else (lambda: datetime.now(UTC))

    async def build(
        self,
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        study_id: str,
        recipient: str,
        requested_by: str,
        spec: ResearchExtractSpec,
        cohort: Cohort,
        k: int,
        candidates: Sequence[SubjectRow],
    ) -> PseudonymisedExtract:
        """Serve an extract, or refuse. There is no partial result."""
        check_export_field(study_id, what="study_id")
        check_export_field(recipient, what="recipient")
        check_export_field(requested_by, what="requested_by")

        if k < K_ANONYMITY_FLOOR:
            # Raised before anything is read: an under-floor request is a
            # programming error, not a refusal about this cohort.
            raise ThresholdBelowFloor(
                f"k={k} is below the platform floor of {K_ANONYMITY_FLOOR} "
                "(files/06 §8; files/09 §4; files/10 §9 learning row)"
            )

        study = await self._resolve_study(spec, study_id, requested_by)

        if not study.approves(recipient):
            raise await self._refuse(
                spec,
                study_id,
                requested_by,
                ResearchRefusalReason.RECIPIENT_NOT_APPROVED,
                f"{recipient!r} is not on study {study_id!r}'s approved recipient list",
            )

        await self._check_retention(spec, study_id, requested_by)
        # INT-262 — read the register for prior extracts of the same study+spec
        # and refuse an overlapping window. Runs on the window alone, before any
        # patient row is read: a request that was always going to refuse never
        # reaches the consent filter or the cross-tab.
        await self._check_differencing(spec, study, requested_by, cohort)
        await self._check_rows(spec, study_id, requested_by, candidates)

        consented = await self._consented(session, tenant_id=tenant_id, candidates=candidates)
        measurement = await self._materialise(spec, study_id, requested_by, consented, cohort, k)

        rows = tuple(
            PseudonymisedRow(
                pseudonym=self._pseudonym(study_id, row.patient_id),
                dimensions=dict(row.dimensions),
                measures=dict(row.measures),
            )
            for row in consented
        )
        digest = hashlib.sha256(canonical_bytes(spec.name, study_id, rows)).hexdigest()
        extract = PseudonymisedExtract(
            study_id=study.study_id,
            ethics_approval_id=study.ethics_approval_id,
            protocol_version=study.protocol_version,
            recipient=recipient,
            spec_name=spec.name,
            measurement=measurement,
            rows=rows,
            content_sha256=digest,
            built_at=self._clock(),
        )
        self._register.append(
            ExtractRecord(
                content_sha256=digest,
                study_id=study.study_id,
                ethics_approval_id=study.ethics_approval_id,
                protocol_version=study.protocol_version,
                recipient=recipient,
                requested_by=requested_by,
                spec_name=spec.name,
                window_start=cohort.window_start.isoformat(),
                window_end=cohort.window_end.isoformat(),
                subjects=len(rows),
                k=k,
                recorded_at=ExtractRegister.recorded_at(extract.built_at),
            )
        )
        await self._audit.record(
            actor=requested_by,
            action="research.extract.served",
            resource_ref=f"extract:{digest}",
            consent_scope=f"scope:{RESEARCH_SCOPE}",
        )
        RESEARCH_EXTRACT_SERVED.labels(spec=spec.name).inc()
        return extract

    # --- gates ------------------------------------------------------------------

    async def _resolve_study(
        self, spec: ResearchExtractSpec, study_id: str, requested_by: str
    ) -> StudyRecord:
        try:
            return self._registry.resolve(study_id, on=self._clock().date())
        except StudyRegistryRefusal as exc:
            if isinstance(exc, StudyApprovalLapsedError):
                reason = ResearchRefusalReason.APPROVAL_LAPSED
            elif isinstance(exc, StudyApprovalNotYetInForceError):
                reason = ResearchRefusalReason.APPROVAL_NOT_IN_FORCE
            else:
                reason = ResearchRefusalReason.UNKNOWN_STUDY
            await self._record_refusal(spec, study_id, requested_by, reason.value)
            raise

    async def _check_retention(
        self, spec: ResearchExtractSpec, study_id: str, requested_by: str
    ) -> None:
        row = self._retention.class_for(DestroyableClass.RESEARCH_EXTRACTS)
        if (
            row.status is ClassStatus.SOURCED
            and row.retention.kind is not RetentionKind.UNSPECIFIED
        ):
            return
        raise await self._refuse(
            spec,
            study_id,
            requested_by,
            ResearchRefusalReason.RETENTION_UNSET,
            "the research_extracts retention class is draft_needs_source — files/06 §3 "
            "says 'per ethics protocol' and no ethics protocol exists (HB-I8). Data whose "
            "destruction date nobody can state may not be created (KVKK m.7, DEST-2017)",
        )

    async def _check_differencing(
        self,
        spec: ResearchExtractSpec,
        study: StudyRecord,
        requested_by: str,
        cohort: Cohort,
    ) -> None:
        """Refuse a window that overlaps a prior extract of the same study+spec.

        INT-230's k gate holds for one extract; two extracts over overlapping
        windows can be *differenced* to recover the cells in the difference, at
        any k. This gate counts the extracts already served for this study and
        spec whose window intersects the requested one — the register holds
        exactly those (study, spec, window) facts, and only for extracts that
        were actually served, so a prior *refusal* never counts against a study.

        Windows are half-open ``[start, end)``: two intersect iff each starts
        before the other ends, so an adjacent window (one starting where the
        other ends) does not overlap. If nothing overlaps, the request is not a
        differencing request and passes.

        The budget is the study's, and it has no default. A study that states
        none refuses every overlapping window (``UNBUDGETED``, fail closed); a
        study that states :class:`~intake_platform.research.studies.QueryBudget`
        permits overlap up to its explicit count and refuses beyond it
        (``EXHAUSTED``). Neither refusal echoes the window or the cohort size.
        """
        window_start = cohort.window_start
        window_end = cohort.window_end
        prior_overlapping = 0
        for record in self._register.for_study(study.study_id):
            if record.spec_name != spec.name:
                continue
            prior_start = datetime.fromisoformat(record.window_start)
            prior_end = datetime.fromisoformat(record.window_end)
            if window_start < prior_end and prior_start < window_end:
                prior_overlapping += 1

        if prior_overlapping == 0:
            return

        budget = study.query_budget
        if budget is None:
            raise await self._refuse(
                spec,
                study.study_id,
                requested_by,
                ResearchRefusalReason.OVERLAPPING_WINDOW_UNBUDGETED,
                "this window overlaps a prior extract of the same study and spec, and the "
                "study states no query budget. A second overlapping extract can be "
                "differenced against the first to recover the cells in the difference "
                "(INT-262). The budget has no default: absent means refuse (HB-R1, "
                "invariant 17). The window is not echoed",
            )
        if prior_overlapping >= budget.max_overlapping_extracts:
            raise await self._refuse(
                spec,
                study.study_id,
                requested_by,
                ResearchRefusalReason.QUERY_BUDGET_EXHAUSTED,
                "this window overlaps more prior extracts of the same study and spec than "
                "the study's query budget permits (INT-262). The window and the count are "
                "not echoed",
            )

    async def _check_rows(
        self,
        spec: ResearchExtractSpec,
        study_id: str,
        requested_by: str,
        candidates: Sequence[SubjectRow],
    ) -> None:
        """Shape, vocabulary and measure checks run over EVERY candidate —
        before the consent filter, so a free-text value cannot be quietly
        carried away by the same pass that drops a non-consenting patient."""
        for row in candidates:
            if set(row.dimensions) != set(spec.dimensions):
                raise await self._refuse(
                    spec,
                    study_id,
                    requested_by,
                    ResearchRefusalReason.DIMENSION_SET_MISMATCH,
                    "a candidate row's dimensions are not the spec's declared set",
                )
            for dimension, value in row.dimensions.items():
                try:
                    check_export_value(dimension, value)
                except ResearchExportRefused as exc:
                    await self._record_refusal(spec, study_id, requested_by, exc.reason.value)
                    raise
                if value not in spec.dimensions[dimension]:
                    raise await self._refuse(
                        spec,
                        study_id,
                        requested_by,
                        ResearchRefusalReason.VALUE_OUTSIDE_VOCABULARY,
                        f"a value of {dimension!r} is not a declared member of its "
                        "vocabulary; the refused value is not echoed",
                    )
            if set(row.measures) != set(spec.measures):
                raise await self._refuse(
                    spec,
                    study_id,
                    requested_by,
                    ResearchRefusalReason.MEASURE_NOT_A_COUNT,
                    "a candidate row's measures are not the spec's declared set",
                )
            for measure, count in row.measures.items():
                if isinstance(count, bool) or not isinstance(count, int):
                    raise await self._refuse(
                        spec,
                        study_id,
                        requested_by,
                        ResearchRefusalReason.MEASURE_NOT_A_COUNT,
                        f"measure {measure!r} is not a count",
                    )

    async def _consented(
        self,
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        candidates: Sequence[SubjectRow],
    ) -> tuple[SubjectRow, ...]:
        """Drop every subject who does not hold the `research` scope.

        Dropped, never flagged: the returned tuple simply does not contain
        them, nothing counts them, and no refusal reason travels. Evaluation
        goes through :func:`~intake_platform.consent.consent_state`, the same
        function the API's ``ensure_consent`` calls — there is one consent
        evaluator and this is not a second one. A withdrawn grant, an absent
        grant and a grant bound to a superseded text are all "not allowed" and
        are all treated identically here.
        """
        kept: list[SubjectRow] = []
        decided: dict[uuid.UUID, bool] = {}
        for row in candidates:
            allowed = decided.get(row.patient_id)
            if allowed is None:
                decision = await consent_state(
                    session,
                    tenant_id=tenant_id,
                    patient_id=row.patient_id,
                    scope=RESEARCH_SCOPE,
                    catalog=self._catalog,
                )
                allowed = decision.allowed
                decided[row.patient_id] = allowed
            if allowed:
                kept.append(row)
        return tuple(kept)

    async def _materialise(
        self,
        spec: ResearchExtractSpec,
        study_id: str,
        requested_by: str,
        consented: Sequence[SubjectRow],
        cohort: Cohort,
        k: int,
    ) -> Measurement:
        """Gate the quasi-identifier cross-tab through the INT-171 helper.

        A "cell" is one combination of the declared dimensions and its
        ``subjects`` is the number of distinct patients wearing it, so a
        combination unique to one person refuses — and refuses the WHOLE
        extract, because a reader given every combination but one recovers it
        by subtraction. An empty cohort refuses with the identical message, so
        "refused" never means "someone was there".
        """
        subjects: dict[tuple[str, ...], set[uuid.UUID]] = defaultdict(set)
        measures: dict[tuple[str, ...], dict[str, int]] = defaultdict(dict)
        keys = tuple(spec.dimensions)
        for row in consented:
            key = tuple(row.dimensions[name] for name in keys)
            subjects[key].add(row.patient_id)
            bucket = measures[key]
            for measure, count in row.measures.items():
                bucket[measure] = bucket.get(measure, 0) + count
        cells = tuple(
            Cell(
                dimensions=dict(zip(keys, key, strict=True)),
                subjects=len(subjects[key]),
                # One study, one site (TCKAY m.5/6, HB-L1): the tenant count is
                # a count here for the same reason it is one in INT-171 — it
                # must never become a label.
                tenants=1,
                measures=measures[key],
            )
            for key in sorted(subjects)
        )
        try:
            return materialise(spec.view, cells, cohort=cohort, k=k)
        except KAnonymityRefusal as exc:
            # INT-171 owns the k reason classes (below_k, dimension_set_mismatch,
            # …); the audit carries that class verbatim rather than a second
            # enum this package would have to keep in step.
            await self._record_refusal(spec, study_id, requested_by, exc.reason.value)
            raise

    # --- refusal bookkeeping ----------------------------------------------------

    async def _refuse(
        self,
        spec: ResearchExtractSpec,
        study_id: str,
        requested_by: str,
        reason: ResearchRefusalReason,
        detail: str,
    ) -> ResearchExportRefused:
        await self._record_refusal(spec, study_id, requested_by, reason.value)
        return ResearchExportRefused(reason, detail)

    async def _record_refusal(
        self,
        spec: ResearchExtractSpec,
        study_id: str,
        requested_by: str,
        reason: str,
    ) -> None:
        """A refused request produced no extract, so it does not enter the
        register — it enters the hash chain, carrying the reason CLASS in the
        action name and nothing about the cohort."""
        RESEARCH_EXTRACT_REFUSED.labels(spec=spec.name, reason=reason).inc()
        await self._audit.record(
            actor=requested_by,
            action=f"research.extract.refused.{reason}",
            resource_ref=f"study:{study_id}",
            consent_scope=f"scope:{RESEARCH_SCOPE}",
        )

    def _pseudonym(self, study_id: str, patient_id: uuid.UUID) -> str:
        """Study-scoped: the same patient in two studies gets two unrelated
        pseudonyms, so two extracts cannot be joined by an investigator who
        holds both. Keyed (invariant 14), which is also exactly why the result
        is pseudonymisation and not anonymisation."""
        return self._tokenizer.pseudonym(f"research:{study_id}:{patient_id}")
