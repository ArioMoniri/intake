"""The failover order — read from the self-hosting registry, never restated.

The INT-100 acceptance says *"failover order from probes registry"*, and
``observability/registry.yaml`` (INT-022) already carries it: every row has a
``fallback`` that is ``none``, ``component:<name>`` or ``in-process:<module>``.
So an order is a walk: start at the entry component and follow
``component:`` links until the chain ends. For the dynamic TTS path that walk
is files/03 §4.9.1 row 11 → row 12 (``voxcpm2-tts`` → ``freya-tts``), which
is what §4.9.4 row 11 prescribes — *"fall to … row 12 for the rest of the
session, then to ``typed``"* — and the reason it is read rather than typed
here is that the registry is the enforcement point files/08 names for
*"set fallback order"*. A second list in code would be a second opinion.

**CLAUDE.md invariant 19, as a refusal.** On the PHI path every lane in the
walk must be ``self_hostable`` *and* cleared for ``phi_path``. A row that is
neither is a cloud vendor, and :class:`CloudFailoverRefused` is raised — the
chain is **refused, not truncated**, because a registry that names a cloud
fallback behind a PHI lane is a defect in the registry, and silently dropping
the row would hide it until the day the primary died. The refusal lives in
:class:`FailoverOrder` itself, so it holds for every order object however it
was built, not only for the ones this module's builder returns.

Off the PHI path (a dev/synthetic bridge — the same ``phi_path=False`` the
ASR adapter already has) a non-self-hostable lane may appear, and then only
**after** every self-hosted one: "self-hosted lanes first" is a stable
partition, and :class:`SelfHostedNotFirst` refuses an order that breaks it.

Two walk rules that are findings rather than preferences:

- a row with ``self_hosted_now: false`` is **skipped and the walk continues
  through it** — the release gate treats exactly that flag as "enabled", and a
  planned lane is not a lane anybody can fail over *to*;
- an ``in-process:`` fallback ends the walk — it is code inside the component
  (the de-identification model's regex floor), not a speech lane.

**One file, one meaning.** ``intake_probes.registry`` is the authoritative
validator. This module reads the same file with a permissive model — the five
fields an order needs — and a contract test asserts the two agree row for row,
exactly as :mod:`intake_voice_runtime.adapters.pins` does.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Final

import yaml
from pydantic import BaseModel, ConfigDict

from intake_voice_runtime.adapters.pins import REGISTRY_PATH
from intake_voice_runtime.profiles import VoiceProfile

__all__ = [
    "CloudFailoverRefused",
    "FailoverChainBroken",
    "FailoverOrder",
    "FailoverRefused",
    "LaneOffPhiPath",
    "LaneRow",
    "NoServingLane",
    "ProfileHasNoSpeechLanes",
    "SelfHostedNotFirst",
    "build_failover_order",
    "failover_order",
    "load_lane_rows",
]

_COMPONENT_PREFIX: Final = "component:"


class FailoverRefused(RuntimeError):
    """Base for every refusal to produce a failover order."""


class CloudFailoverRefused(FailoverRefused):
    """A PHI-path order reached a lane that is not self-hostable (invariant 19)."""


class LaneOffPhiPath(FailoverRefused):
    """A PHI-path order reached a self-hostable lane not cleared for PHI."""


class SelfHostedNotFirst(FailoverRefused):
    """A non-self-hostable lane precedes a self-hosted one (invariant 19)."""


class FailoverChainBroken(FailoverRefused):
    """The walk named a component the registry lacks, or went round in a loop."""


class NoServingLane(FailoverRefused):
    """Every lane on the chain is planned; there is nothing to fail over to."""


class ProfileHasNoSpeechLanes(FailoverRefused):
    """``typed`` synthesises nothing (files/03 §4.4), so it has no speech order."""


class LaneRow(BaseModel):
    """The five registry fields an order needs. Validation proper is intake_probes'."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    component: str
    self_hostable: bool
    self_hosted_now: bool
    phi_path: bool
    fallback: str

    @property
    def fallback_component(self) -> str | None:
        """The next component in the walk, or ``None`` where the chain ends."""
        if self.fallback.startswith(_COMPONENT_PREFIX):
            return self.fallback[len(_COMPONENT_PREFIX) :]
        return None


@dataclass(frozen=True)
class FailoverOrder:
    """The lanes a session may speak through, most preferred first.

    Its constructor is where invariant 19 is enforced, so the guarantee does
    not depend on which function built the object.
    """

    entry: str
    lanes: tuple[LaneRow, ...]
    phi_path: bool

    def __post_init__(self) -> None:
        if not self.lanes:
            raise NoServingLane(
                f"no lane on the chain from {self.entry!r} is running "
                "(self_hosted_now: false on every row); a session that cannot speak "
                "is composed typed, not handed an empty ladder"
            )
        if self.phi_path:
            for lane in self.lanes:
                if not lane.self_hostable:
                    raise CloudFailoverRefused(
                        f"the failover chain from {self.entry!r} reaches {lane.component!r}, "
                        "which is not self-hostable. residency_tr never fails over to a "
                        "cloud vendor on the PHI path (CLAUDE.md invariant 19; files/00 "
                        "§0b); fix the registry row's fallback rather than the order"
                    )
                if not lane.phi_path:
                    raise LaneOffPhiPath(
                        f"the failover chain from {self.entry!r} reaches {lane.component!r}, "
                        "which the registry does not clear for the PHI path; a PHI "
                        "session may not fail over to it"
                    )
        seen_cloud = False
        for lane in self.lanes:
            if not lane.self_hostable:
                seen_cloud = True
            elif seen_cloud:
                raise SelfHostedNotFirst(
                    f"self-hosted lane {lane.component!r} is ordered after a lane that "
                    "is not self-hostable; self-hosted lanes come first (CLAUDE.md "
                    "invariant 19)"
                )

    @property
    def components(self) -> tuple[str, ...]:
        return tuple(lane.component for lane in self.lanes)


@lru_cache(maxsize=4)
def _read(path: Path) -> Mapping[str, LaneRow]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    parsed = (LaneRow.model_validate(entry) for entry in document["components"])
    return {row.component: row for row in parsed}


def load_lane_rows(registry_path: Path | None = None) -> Mapping[str, LaneRow]:
    """Every registry row, keyed by component, as an order reads it."""
    return _read(registry_path or REGISTRY_PATH)


def build_failover_order(
    entry: str, rows: Mapping[str, LaneRow], *, phi_path: bool
) -> FailoverOrder:
    """Walk the fallback chain from ``entry`` and order what is running."""
    walked: list[LaneRow] = []
    visited: set[str] = set()
    component: str | None = entry
    while component is not None:
        if component in visited:
            raise FailoverChainBroken(
                f"the fallback chain from {entry!r} returns to {component!r}; a loop is "
                "not an order"
            )
        visited.add(component)
        row = rows.get(component)
        if row is None:
            raise FailoverChainBroken(
                f"the fallback chain from {entry!r} names {component!r}, which is not in "
                "observability/registry.yaml"
            )
        if row.self_hosted_now:
            walked.append(row)
        component = row.fallback_component
    self_hosted = tuple(row for row in walked if row.self_hostable)
    elsewhere = tuple(row for row in walked if not row.self_hostable)
    return FailoverOrder(entry=entry, lanes=self_hosted + elsewhere, phi_path=phi_path)


def failover_order(
    entry: str,
    *,
    profile: VoiceProfile,
    phi_path: bool = True,
    registry_path: Path | None = None,
) -> FailoverOrder:
    """The order a ``residency_tr`` session fails over in, from the registry."""
    if profile is VoiceProfile.TYPED:
        raise ProfileHasNoSpeechLanes(
            "the typed profile has no speech lane to fail over between: it renders "
            "to a screen and synthesises nothing (files/03 §4.4; ADR-010)"
        )
    return build_failover_order(entry, load_lane_rows(registry_path), phi_path=phi_path)
