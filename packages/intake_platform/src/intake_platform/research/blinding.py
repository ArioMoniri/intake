"""INT-231 — blinded exports: hide the study-arm/condition label from the analyst.

An analyst comparing arms must not know which arm is which while they analyse,
or the comparison is not blind. This layer takes a
:class:`~intake_platform.research.artefact.PseudonymisedExtract` — already
consent-gated, k-gated and pseudonymised by INT-230/INT-262 — and replaces the
values of the designated ARM dimension(s) with opaque blind codes
(``condition_1``, ``condition_2``, …). The real labels (``residency_tr``,
``typed``) never appear in the blinded artefact.

**The code is a keyed permutation, not a naming that leaks the mapping.** Codes
are assigned in the order of a keyed HMAC of the arm value, so ``condition_1``
is neither the alphabetically-first arm nor the largest — the analyst cannot
read the arm off the code. The code↔arm map is a SEPARATE sealed artefact
(:class:`BlindingCodebook`) held by the unblinding authority (the trial
statistician / DSMB); it is returned apart from the extract so the export path
routes the data to the analyst and the codebook to the authority, never
together.

**Re-identification is refused without the sealed codebook.** The blinded
extract holds no real arm label and no reference to the codebook, and
:func:`unblind` refuses a codebook that belongs to a different study or spec —
so the mapping cannot be recovered from the blinded data alone.

**It builds on the export gate and fails closed.** :class:`BlindedExportGate`
composes :class:`~intake_platform.research.extract.ResearchExportGate` with the
blinder: with the shipped EMPTY study registry there is no study to serve, so a
blinded export refuses exactly where INT-230 refuses (HB-R1 — nothing to be
blinded from until a study is registered).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from intake_platform.research.artefact import PseudonymisedExtract
from intake_platform.research.extract import ResearchExportGate
from intake_platform.research.values import ResearchExtractSpec
from intake_platform.tokenization import Tokenizer

__all__ = [
    "BLIND_CODE_PREFIX",
    "BlindedExportGate",
    "BlindedExtract",
    "BlindedRow",
    "BlindingCodebook",
    "ReidentificationRefused",
    "blind_extract",
    "unblind",
]

#: Blind codes read unmistakably as blinded, and sit outside any real dimension
#: vocabulary so they can never be confused with a real arm.
BLIND_CODE_PREFIX = "condition_"


class ReidentificationRefused(Exception):
    """A blinding could not be produced, or an unblinding was attempted without
    the matching sealed codebook. The refusal carries no arm label."""


@dataclass(frozen=True)
class BlindedRow:
    """One row with its arm dimension(s) replaced by blind codes."""

    pseudonym: str
    dimensions: Mapping[str, str]
    measures: Mapping[str, int]


@dataclass(frozen=True)
class BlindedExtract:
    """A blinded extract, safe to hand to an analyst. It carries no real arm
    label and no reference to the codebook that would recover one."""

    study_id: str
    ethics_approval_id: str
    protocol_version: str
    recipient: str
    spec_name: str
    #: Which dimensions were blinded — the analyst may know WHICH axis is masked
    #: without knowing the mapping on it.
    blinded_dimensions: tuple[str, ...]
    rows: tuple[BlindedRow, ...]
    content_sha256: str
    built_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def subjects(self) -> int:
        return len(self.rows)


@dataclass(frozen=True)
class BlindingCodebook:
    """The sealed code↔arm map. Held by the unblinding authority ONLY — never
    shipped with the :class:`BlindedExtract`. One inner map per blinded
    dimension: ``{blind_code: real_value}``."""

    study_id: str
    spec_name: str
    mapping: Mapping[str, Mapping[str, str]]


def _blind_codes(
    study_id: str,
    spec_name: str,
    dimension: str,
    real_values: Sequence[str],
    blinder: Tokenizer,
) -> dict[str, str]:
    """Assign ``condition_N`` codes to the distinct real values in a keyed order.

    Ordering by the HMAC of the value (not by spelling, not by count) is what
    makes the code non-informative: two different keys can assign the codes the
    other way round, so the code reveals nothing about which real arm it stands
    for.
    """
    ordered = sorted(
        set(real_values),
        key=lambda value: blinder.pseudonym(f"blind:{study_id}:{spec_name}:{dimension}:{value}"),
    )
    return {real: f"{BLIND_CODE_PREFIX}{index + 1}" for index, real in enumerate(ordered)}


def blind_extract(
    extract: PseudonymisedExtract,
    *,
    arm_dimensions: Sequence[str],
    blinder: Tokenizer,
) -> tuple[BlindedExtract, BlindingCodebook]:
    """Blind ``arm_dimensions`` in ``extract``. Returns the blinded extract and,
    apart from it, the sealed codebook.

    Refuses (:class:`ReidentificationRefused`) if an arm dimension is not present
    on every row — a dimension the extract does not carry cannot be blinded, and
    silently skipping it would leave a real label in the data.
    """
    if not arm_dimensions:
        raise ReidentificationRefused("no arm dimension named: nothing to blind")

    for dimension in arm_dimensions:
        for row in extract.rows:
            if dimension not in row.dimensions:
                raise ReidentificationRefused(
                    f"arm dimension {dimension!r} is not present on every row; a dimension "
                    "the extract does not carry cannot be blinded"
                )

    real_to_code: dict[str, dict[str, str]] = {}
    code_to_real: dict[str, dict[str, str]] = {}
    for dimension in arm_dimensions:
        values = [row.dimensions[dimension] for row in extract.rows]
        codes = _blind_codes(extract.study_id, extract.spec_name, dimension, values, blinder)
        real_to_code[dimension] = codes
        code_to_real[dimension] = {code: real for real, code in codes.items()}

    blinded_rows = tuple(
        BlindedRow(
            pseudonym=row.pseudonym,
            dimensions={
                name: (real_to_code[name][value] if name in real_to_code else value)
                for name, value in row.dimensions.items()
            },
            measures=dict(row.measures),
        )
        for row in extract.rows
    )
    blinded_dimensions = tuple(arm_dimensions)
    digest = _canonical_digest(
        extract.study_id, extract.spec_name, blinded_dimensions, blinded_rows
    )
    blinded = BlindedExtract(
        study_id=extract.study_id,
        ethics_approval_id=extract.ethics_approval_id,
        protocol_version=extract.protocol_version,
        recipient=extract.recipient,
        spec_name=extract.spec_name,
        blinded_dimensions=blinded_dimensions,
        rows=blinded_rows,
        content_sha256=digest,
        built_at=extract.built_at,
    )
    codebook = BlindingCodebook(
        study_id=extract.study_id,
        spec_name=extract.spec_name,
        mapping=code_to_real,
    )
    return blinded, codebook


def unblind(blinded: BlindedExtract, codebook: BlindingCodebook) -> BlindedExtract:
    """Recover the real arm labels using the sealed codebook.

    This is the unblinding authority's operation, not the analyst's. It refuses a
    codebook that belongs to a different study or spec, and refuses a code with
    no entry in the codebook — so re-identification cannot be forged from a
    mismatched or partial map.
    """
    if codebook.study_id != blinded.study_id or codebook.spec_name != blinded.spec_name:
        raise ReidentificationRefused(
            "the codebook does not belong to this extract (study or spec mismatch); "
            "an extract cannot be unblinded with another study's codebook"
        )
    restored_rows: list[BlindedRow] = []
    for row in blinded.rows:
        dimensions = dict(row.dimensions)
        for dimension in blinded.blinded_dimensions:
            code = dimensions[dimension]
            inner = codebook.mapping.get(dimension, {})
            if code not in inner:
                raise ReidentificationRefused(
                    f"blind code in {dimension!r} has no entry in the codebook; "
                    "the map cannot be completed"
                )
            dimensions[dimension] = inner[code]
        restored_rows.append(
            BlindedRow(pseudonym=row.pseudonym, dimensions=dimensions, measures=dict(row.measures))
        )
    return BlindedExtract(
        study_id=blinded.study_id,
        ethics_approval_id=blinded.ethics_approval_id,
        protocol_version=blinded.protocol_version,
        recipient=blinded.recipient,
        spec_name=blinded.spec_name,
        blinded_dimensions=(),
        rows=tuple(restored_rows),
        content_sha256=blinded.content_sha256,
        built_at=blinded.built_at,
    )


def _canonical_digest(
    study_id: str,
    spec_name: str,
    blinded_dimensions: tuple[str, ...],
    rows: Sequence[BlindedRow],
) -> str:
    payload = {
        "study_id": study_id,
        "spec": spec_name,
        "blinded_dimensions": sorted(blinded_dimensions),
        "rows": sorted(
            (
                {
                    "pseudonym": row.pseudonym,
                    "dimensions": dict(sorted(row.dimensions.items())),
                    "measures": dict(sorted(row.measures.items())),
                }
                for row in rows
            ),
            key=lambda row: str(row["pseudonym"]),
        ),
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(blob).hexdigest()


class BlindedExportGate:
    """A research export that blinds the arm dimension before it leaves.

    Composition, not a second gate: :class:`ResearchExportGate` owns every
    permission check (consent, ethics approval, recipient, retention, k, the
    differencing window), and this wrapper blinds the artefact it returns. So a
    blinded export inherits every refusal of the export gate — including the one
    that matters most today, the empty registry (HB-R1).
    """

    def __init__(self, export_gate: ResearchExportGate, *, blinder: Tokenizer) -> None:
        self._export_gate = export_gate
        self._blinder = blinder

    async def build(
        self,
        session: object,
        *,
        tenant_id: uuid.UUID,
        study_id: str,
        recipient: str,
        requested_by: str,
        spec: ResearchExtractSpec,
        cohort: object,
        k: int,
        candidates: Sequence[object],
        arm_dimensions: Sequence[str],
    ) -> tuple[BlindedExtract, BlindingCodebook]:
        extract = await self._export_gate.build(
            session,  # type: ignore[arg-type]
            tenant_id=tenant_id,
            study_id=study_id,
            recipient=recipient,
            requested_by=requested_by,
            spec=spec,
            cohort=cohort,  # type: ignore[arg-type]
            k=k,
            candidates=candidates,  # type: ignore[arg-type]
        )
        return blind_extract(extract, arm_dimensions=arm_dimensions, blinder=self._blinder)
