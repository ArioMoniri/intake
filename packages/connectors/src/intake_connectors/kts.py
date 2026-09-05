"""The KTS (SBYS Kayıt Tescil) application pack (INT-162).

A hospital-side module is an SBYS, and an SBYS must be KTS-registered before it
is contracted to a hospital (files/06 §63, legal source SBYS-6). This module
generates the registration pack **from repo docs**: it reads a committed
checklist derived verbatim from files/06 §63, anchors each satisfied item to
where this repository already meets the duty, and renders the whole into
``docs/regulatory/kts_pack.md``.

It follows the docs/legal pattern (INT-210): the mechanism ships complete and
the human-legal content fails closed. The required-document list is SBSGM's to
publish and no committed source holds it, so that item — and the USVS
dictionary the code bindings need — come back ``blocked`` and
:meth:`KtsPack.is_complete` is ``False``. A pack that claimed completeness on
content nobody supplied would be exactly the plausible-but-unsigned artefact
invariant 17 forbids.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from intake_connectors.dpa import processor_role_references

__all__ = [
    "KTS_REQUIREMENTS_PATH",
    "KtsPack",
    "KtsPackError",
    "KtsRequirement",
    "build_kts_pack",
]

#: The committed checklist ships beside this module.
KTS_REQUIREMENTS_PATH = Path(__file__).resolve().parent / "kts_requirements.yaml"

#: The repository root, from which every ``repo_anchor`` is resolved.
_REPO_ROOT = Path(__file__).resolve().parents[4]


class KtsPackError(Exception):
    """The checklist is malformed, or a present item anchors to a missing file."""


@dataclass(frozen=True)
class KtsRequirement:
    """One checklist row: satisfied and anchored, or blocked and named."""

    id: str
    title: str
    status: Literal["present", "blocked"]
    repo_anchor: str | None
    blocked_reason: str | None


@dataclass(frozen=True)
class KtsPack:
    """The generated pack: its requirements, and whether it is complete."""

    version: int
    requirements: tuple[KtsRequirement, ...]

    def is_complete(self) -> bool:
        """Complete only when nothing is blocked. A single blocked item — the
        SBSGM list, the USVS dictionary — keeps the pack unfinished, because a
        registration is not ready while a required artefact is absent."""
        return not self.blocked()

    def blocked(self) -> tuple[KtsRequirement, ...]:
        return tuple(item for item in self.requirements if item.status == "blocked")

    def render_markdown(self) -> str:
        lines: list[str] = [
            "# KTS (SBYS Kayıt Tescil) application pack",
            "",
            "> GENERATED from `packages/connectors/src/intake_connectors/kts_requirements.yaml`",
            "> by `intake_connectors.kts.build_kts_pack` (INT-162). Do not edit by hand — a",
            "> test asserts this file equals the generator's output. Legal source: files/06",
            "> §63 (SBYS-6). The pack is NOT complete: the human-legal items are blocked and",
            "> fail closed, exactly as `docs/legal/documents.yaml` does.",
            "",
            f"Pack version: {self.version}  ·  complete: {str(self.is_complete()).lower()}",
            "",
            "## Requirements",
            "",
            "| id | requirement | status | anchor |",
            "| --- | --- | --- | --- |",
        ]
        for item in self.requirements:
            anchor = item.repo_anchor if item.repo_anchor is not None else "—"
            lines.append(f"| {item.id} | {item.title} | {item.status} | {anchor} |")
        lines += ["", "## Blocked — awaiting a named human", ""]
        if self.blocked():
            for item in self.blocked():
                reason = " ".join((item.blocked_reason or "").split())
                lines.append(f"- **{item.id}** — {reason}")
        else:  # pragma: no cover - the pack ships with blocked items today
            lines.append("- (none)")
        lines += [
            "",
            "See `docs/backlog/blockers.md` (INT-162) and `files/HUMAN_BLOCKERS.md` for the",
            "one sentence each blocked item needs answered.",
            "",
            "## Processor-role DPA clauses (files/06 §7)",
            "",
            "The executed DPA is HB-A15's to supply; these are the clauses it must carry.",
            "",
            "| clause | requirement | anchor |",
            "| --- | --- | --- |",
        ]
        for clause in processor_role_references():
            requirement = " ".join(clause.requirement.split())
            lines.append(f"| {clause.id} | {requirement} | {clause.repo_anchor} |")
        lines.append("")
        return "\n".join(lines)


class _RequirementRow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    status: Literal["present", "blocked"]
    repo_anchor: str | None = None
    blocked_reason: str | None = None


class _RequirementsFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int = Field(ge=1)
    requirements: list[_RequirementRow] = Field(min_length=1)


def build_kts_pack(requirements_path: Path | None = None, repo_root: Path | None = None) -> KtsPack:
    """Read the committed checklist and render the pack, verifying anchors."""
    path = requirements_path if requirements_path is not None else KTS_REQUIREMENTS_PATH
    root = repo_root if repo_root is not None else _REPO_ROOT
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise KtsPackError(f"{path} is not a mapping")
    parsed = _RequirementsFile.model_validate(raw)

    requirements: list[KtsRequirement] = []
    for row in parsed.requirements:
        if row.status == "present":
            if row.repo_anchor is None:
                raise KtsPackError(f"present requirement {row.id!r} names no repo anchor")
            if not (root / row.repo_anchor).exists():
                raise KtsPackError(
                    f"requirement {row.id!r} anchors to {row.repo_anchor!r}, which does not "
                    "exist — a citation to a missing document reads as satisfied and is worse "
                    "than a blocked item"
                )
        elif row.blocked_reason is None:
            raise KtsPackError(f"blocked requirement {row.id!r} names no reason")
        requirements.append(
            KtsRequirement(
                id=row.id,
                title=row.title,
                status=row.status,
                repo_anchor=row.repo_anchor,
                blocked_reason=row.blocked_reason,
            )
        )
    return KtsPack(version=parsed.version, requirements=tuple(requirements))
