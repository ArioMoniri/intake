"""INT-172 — evidence bundles: ids, counts and citations, and nothing else.

files/09 §4 describes what rides with a proposal: "aggregate stats,
de-identified exemplars, simulator run, triage goldens, latency harness,
shadow replay on de-identified transcripts, Langfuse experiment link". This
module builds that bundle with two deliberate departures, both recorded here
rather than left for a reader to notice:

**No exemplars, and no shadow replay over transcripts.** "De-identified
exemplars" of Turkish clinical speech is precisely the claim
files/HUMAN_BLOCKERS.md HB-L6 records as one "Turkish NLP cannot support" —
spaCy ships no Turkish model, names appear in oblique cases (*Ahmet'in*,
*Ayşe'ye*), and files/10 §3 puts the expected residue at 0.3-1.0 direct
identifiers per four-minute intake. INT-171 built the whole analytics layer
without narrative for that reason. A bundle that carried "de-identified"
exemplars would be re-making the claim inside the one artefact a clinician
reads closely. So the exemplar slot is absent, not empty.

**Everything else fails closed rather than being faked.** The simulator run,
the triage goldens, the latency harness, the shadow replay and the Langfuse
experiment are declared as :data:`REQUIRED_CHECKS`, each naming the backlog
issue that produces its artefact and each starting at
:attr:`CheckStatus.NOT_AVAILABLE`. A bundle whose required checks are not all
``PASSED`` is not complete, and :mod:`intake_learning.publisher` refuses to
build a pull request from one. That is invariant 17's shape: build the
mechanism, wire the gate, make it fail closed, leave the content empty.

**The k floor is inherited, never re-declared.** :func:`EvidenceBundle.build`
re-runs :func:`intake_platform.analytics.materialise` over the cells it was
handed, rather than trusting a ``Measurement`` object. A caller can construct
a ``Measurement`` directly — it is a plain frozen dataclass — so the bundle
treats one as untrusted input and puts it back through INT-171's gate: the
id-shape check, the declared-column check and the k >= 10 floor all apply
again on the way into an artefact that leaves the sandbox.

**The only prose in a bundle is committed prose.** A ``Cohort`` carries a
free-text ``description``, so the bundle accepts only the ``cohort_description``
the view registry already commits to, byte for byte. Anything else is refused
without being echoed — the refusal message never repeats what it refused, for
the same reason INT-171's does not (invariant 6).

sec_row: `learning-loops`.  legal: KVKK-16, KSVY-16.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any, Final

from intake_platform.analytics import AnalyticsView, Measurement, materialise
from prometheus_client import Counter

__all__ = [
    "LEARNING_EVIDENCE_BUNDLES",
    "REQUIRED_CHECKS",
    "CheckStatus",
    "EvidenceBundle",
    "EvidenceCheck",
    "EvidenceSource",
]

LEARNING_EVIDENCE_BUNDLES = Counter(
    "learning_evidence_bundles_total",
    "Evidence bundles built for a Loop 2 proposal, by view and completeness. "
    "files/08 §4 group L asks for evidence-bundle completeness as a console "
    "signal; this is it.",
    ["view", "status"],
)


class EvidenceSource(StrEnum):
    """A citation is a member of a closed set, never a string someone typed.

    That is what makes :func:`EvidenceBundle.to_json` free-text-free without a
    scrubber: a citation field cannot hold a sentence because it cannot hold
    anything that is not one of these.
    """

    #: files/09 §4 — Loop 2, its signals, its thresholds and its allowed
    #: proposal types
    FILES_09_S4 = "files/09 §4"
    #: files/09 §6 — the tests that keep the loops honest
    FILES_09_S6 = "files/09 §6"
    #: files/09 §7 — read-only creds, sandbox, PR bot, signed bundles
    FILES_09_S7 = "files/09 §7"
    #: files/06 §8 — the service-improvement purpose and its opt-out
    FILES_06_S8 = "files/06 §8"
    #: files/10 §9 — the `learning-loops` row: threats, controls, signals, tests
    FILES_10_S9 = "files/10 §9 learning-loops"
    #: CLAUDE.md invariant 12 — learning is proposal-only
    CLAUDE_INVARIANT_12 = "CLAUDE.md invariant 12"
    #: CLAUDE.md invariant 20 — a figure is a measurement, never a property
    CLAUDE_INVARIANT_20 = "CLAUDE.md invariant 20"
    #: INT-171 — the de-identified views and the k-anonymity gate this reads
    INT_171_ANALYTICS = "INT-171 analytics"
    #: INT-490 — the research and improvement release the admin panel shows,
    #: already gated within and across views
    INT_490_RESEARCH = "INT-490 research analytics"
    #: LD-06 — what admin research and improvement analytics may hold
    LD_06 = "LD-06"
    #: Test fixtures only. No committed configuration names it, which is why
    #: :meth:`~intake_learning.architect.PromotionThresholds.from_blueprint`
    #: raises instead of returning a floor sourced from here.
    TEST_FIXTURE = "test fixture"


class CheckStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    #: The artefact's producer has not landed. Not a failure and not a pass —
    #: a bundle in this state is incomplete and cannot open a PR.
    NOT_AVAILABLE = "not_available"


@dataclass(frozen=True)
class EvidenceCheck:
    """One artefact files/09 §4 requires alongside a proposal."""

    name: str
    status: CheckStatus
    #: The backlog issue that produces the artefact. Invariant 17: a missing
    #: dependency is named, never mocked.
    supplied_by: str


#: files/09 §4's artefact list minus the exemplars (see the module docstring).
#: Every entry starts NOT_AVAILABLE, because none of the producers has landed
#: on this branch; the statuses become real when the issues named here do.
REQUIRED_CHECKS: Final[tuple[EvidenceCheck, ...]] = (
    EvidenceCheck("simulator_run", CheckStatus.NOT_AVAILABLE, "INT-153"),
    EvidenceCheck("triage_goldens", CheckStatus.NOT_AVAILABLE, "INT-059"),
    EvidenceCheck("latency_harness", CheckStatus.NOT_AVAILABLE, "INT-116"),
    EvidenceCheck("shadow_replay", CheckStatus.NOT_AVAILABLE, "INT-173"),
    EvidenceCheck("langfuse_experiment", CheckStatus.NOT_AVAILABLE, "INT-175"),
)


@dataclass(frozen=True)
class EvidenceBundle:
    """The attachment a clinician reads before approving a proposal."""

    view: str
    #: The registry's own ``cohort_description`` and ``narrative_exclusion``,
    #: carried verbatim so the reader can see what the numbers exclude.
    cohort_description: str
    narrative_exclusion: str
    k: int
    measurements: tuple[Measurement, ...]
    citations: tuple[EvidenceSource, ...]
    checks: tuple[EvidenceCheck, ...]

    @classmethod
    def build(
        cls,
        *,
        view: AnalyticsView,
        measurements: Sequence[Measurement],
        citations: Sequence[EvidenceSource],
        k: int,
    ) -> EvidenceBundle:
        """Re-gate every measurement, then bundle it.

        :raises intake_platform.analytics.ThresholdBelowFloor: ``k`` under the
            blueprint floor.
        :raises intake_platform.analytics.KAnonymityRefusal: a cell is thin or
            not the shape the view declared — including a dimension value that
            is not id-shaped, which is how narrative would arrive.
        :raises ValueError: a measurement names another view, its cohort
            description is not the registry's, or there is no citation.
        """
        if not citations:
            raise ValueError(
                "a proposal without a citation is an assertion. files/09 §4 "
                "requires an evidence bundle; name at least one EvidenceSource"
            )
        if not measurements:
            raise ValueError("an evidence bundle with no measurement demonstrates nothing")

        regated: list[Measurement] = []
        for measurement in measurements:
            if measurement.view != view.name:
                raise ValueError(
                    f"this bundle is for {view.name!r} and was handed a "
                    f"measurement of {measurement.view!r}"
                )
            if measurement.cohort.description != view.cohort_description:
                # Deliberately does not echo the description it refused.
                raise ValueError(
                    f"the cohort description for {view.name!r} must be the "
                    "registry's own, byte for byte. The only prose an evidence "
                    "bundle carries is prose already committed to "
                    "intake_platform.analytics.views (invariant 6)"
                )
            # ``measured_at`` is carried over rather than re-stamped: the
            # instant that belongs in the provenance sentence is when the view
            # was *read*, not when this bundle re-checked it. Re-stamping would
            # also make the digest irreproducible, and a signature over a value
            # nobody can recompute is not evidence.
            regated.append(
                replace(
                    materialise(view, measurement.cells, cohort=measurement.cohort, k=k),
                    measured_at=measurement.measured_at,
                )
            )

        bundle = cls(
            view=view.name,
            cohort_description=view.cohort_description,
            narrative_exclusion=view.narrative_exclusion,
            k=k,
            measurements=tuple(regated),
            citations=tuple(citations),
            checks=REQUIRED_CHECKS,
        )
        LEARNING_EVIDENCE_BUNDLES.labels(
            view=view.name,
            status="complete" if bundle.is_complete else "incomplete",
        ).inc()
        return bundle

    @property
    def is_complete(self) -> bool:
        """files/09 §4's artefact list, satisfied. Today: never — every
        producer named in :data:`REQUIRED_CHECKS` is a later issue."""
        return all(check.status is CheckStatus.PASSED for check in self.checks)

    @property
    def unmet_checks(self) -> tuple[str, ...]:
        return tuple(check.name for check in self.checks if check.status is not CheckStatus.PASSED)

    def as_payload(self) -> dict[str, Any]:
        """The bundle as plain data, in a fixed key order.

        Iterates the dataclass's declared shape rather than the instance, for
        the reason :mod:`intake_platform.observability.spans` gives: nothing an
        ``object.__setattr__`` bolts on afterwards can reach a payload.
        """
        return {
            "view": self.view,
            "k": self.k,
            "cohort_description": self.cohort_description,
            "narrative_exclusion": self.narrative_exclusion,
            "citations": [citation.value for citation in self.citations],
            "checks": [
                {
                    "name": check.name,
                    "status": check.status.value,
                    "supplied_by": check.supplied_by,
                }
                for check in self.checks
            ],
            "complete": self.is_complete,
            "measurements": [
                {
                    "view": measurement.view,
                    "k": measurement.k,
                    "window_start": measurement.cohort.window_start.isoformat(),
                    "window_end": measurement.cohort.window_end.isoformat(),
                    "measured_at": measurement.measured_at.isoformat(),
                    "provenance": measurement.provenance,
                    "cells": [
                        {
                            "dimensions": dict(sorted(cell.dimensions.items())),
                            "subjects": cell.subjects,
                            "tenants": cell.tenants,
                            "measures": dict(sorted(cell.measures.items())),
                        }
                        for cell in measurement.cells
                    ],
                }
                for measurement in self.measurements
            ],
        }

    def to_json(self) -> str:
        """Canonical JSON: sorted keys, no whitespace, ASCII-escaped.

        Byte-for-byte the serialisation :func:`intake_platform.audit._entry_hash`
        uses, and for the same reason — the digest a signature covers must be
        reproducible by an independent implementation reading only the format.
        """
        return json.dumps(
            self.as_payload(), sort_keys=True, separators=(",", ":"), ensure_ascii=True
        )
