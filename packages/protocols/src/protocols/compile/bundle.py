"""The compiled bundle: five artefacts, one hash, byte-identical on re-run.

INT-041's acceptance is three sentences long and each one lives here: *"two
runs produce identical hashes; resolved-protocol hash pinned per session;
compile artifacts under packages/protocols/dist"*.

Determinism is a property of construction rather than of care: every mapping
is emitted with sorted keys, every collection comes out of the resolved
document in resolution order, and nothing in this module reads a clock, an
environment variable or a filesystem path. ``write_bundle`` writes exactly
what ``compile_bundle`` computed, so a second write is a no-op diff.

INT-058 adds the resolved document itself as a sixth artefact and has
``write_bundle`` pack all of them into the signable ``bundle.tar.gz``
(:mod:`protocols.compile.archive`); the runtime half is
:mod:`protocols.serving`.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from clinical_schemas.common import FrozenModel, Sha256
from pydantic import Field

from protocols.bindings import OperationalTemplate
from protocols.compile.archive import write_archive
from protocols.compile.emit_clips import ClipRow, clip_manifest
from protocols.compile.emit_code import pydantic_module, typescript_module
from protocols.compile.emit_fhir import questionnaire
from protocols.compile.errors import CompileError
from protocols.compile.life_threat import LifeThreatSet
from protocols.compile.resolve import ResolvedProtocol, resolve_protocol
from protocols.data_register import DataCategoryRegister
from protocols.licences import LicenceTable
from protocols.loader import PackRegistry
from protocols.locale_text import DEFAULT_LOCALE

__all__ = ["DIST_ROOT", "MANIFEST", "RESOLVED", "CompiledBundle", "compile_bundle", "write_bundle"]

DIST_ROOT = Path("packages/protocols/dist")
"""Where the CLI writes, repo-root relative (INT-041 acceptance)."""

QUESTIONNAIRE = "questionnaire.json"
BINDINGS = "openehr_bindings.json"
PYDANTIC = "slots.py"
TYPESCRIPT = "slots.ts"
MANIFEST = "manifest.json"
RESOLVED = "resolved_protocol.json"
"""The merged document itself (INT-058). files/04 §7 puts "YAML + compiled
outputs" in the signed bundle; this is the chain's YAML after resolution, in
the by-alias JSON form that validates back into :class:`ResolvedProtocol`, so
the runtime re-derives the resolved-protocol hash from content it verified
rather than trusting the number the manifest states."""


class CompiledBundle(FrozenModel):
    """Everything one compile produced, before it touches a filesystem."""

    pack_id: str = Field(description="Target pack.")
    version: str = Field(description="Target pack version.")
    voice: str = Field(description="Voice the clip manifest was keyed for.")
    locale: str = Field(
        default=DEFAULT_LOCALE,
        description="Locale the bundle speaks. The clip manifest keys on "
        "(locale, voice), so the artefact name carries both (INT-297).",
    )
    resolved_protocol_hash: Sha256 = Field(
        description="Pinned per session (files/03 §6; files/12 §8)."
    )
    opt_template_id: str = Field(description="files/12 §8 questionnaire_definition.")
    opt_sha256: Sha256 = Field(description="files/12 §8.1 test_opt_is_pinned.")
    clip_manifest: tuple[ClipRow, ...] = Field(
        default=(), description="text_hash → clip_id per voice (files/03 §6 output (e))."
    )
    artifacts: dict[str, str] = Field(
        description="Relative path → exact file contents, sorted by path."
    )


def _dump(payload: object) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _bindings_rows(document: ResolvedProtocol) -> list[dict[str, Any]]:
    """The files/12 §8 ``slot_definition`` table, one row per slot."""
    return [
        {
            "fhir_link_id": slot.fhir_link_id,
            "section_id": slot.section_id,
            "slot_key": slot.key,
            "slot_type": slot.slot.type.value,
            "aql_path": slot.aql_path,
            "rm_type": slot.rm_type,
            "openehr_deferred_reason": slot.openehr_deferred_reason,
        }
        for section in document.sections
        for slot in section.slots
    ]


def compile_bundle(
    *,
    pack_id: str,
    registry: PackRegistry,
    life_threat: LifeThreatSet,
    template: OperationalTemplate,
    voice: str,
    overlays: Sequence[str] = (),
    licences: LicenceTable | None = None,
    locale: str = DEFAULT_LOCALE,
    data_register: DataCategoryRegister | None = None,
) -> CompiledBundle:
    """Resolve, project, and hash. Raises :class:`CompileError` on any refusal.

    ``data_register`` gates tagged slots (INT-349); omitted, it has no rows."""
    document = resolve_protocol(
        pack_id=pack_id,
        registry=registry,
        life_threat=life_threat,
        template=template,
        overlays=overlays,
        licences=licences,
        locale=locale,
        data_register=data_register,
    )
    clips, prompts, clip_refusals = clip_manifest(document, voice, locale=locale)
    doc, fhir_refusals = questionnaire(document, prompts)
    refusals = (*clip_refusals, *fhir_refusals)
    if refusals:
        raise CompileError(refusals)
    artifacts: dict[str, str] = {
        QUESTIONNAIRE: _dump(doc),
        RESOLVED: _dump(document.model_dump(mode="json", by_alias=True)),
        BINDINGS: _dump(_bindings_rows(document)),
        PYDANTIC: pydantic_module(document),
        TYPESCRIPT: typescript_module(document),
        f"clips.{locale}.{voice}.json": _dump(
            {
                "voice": voice,
                "locale": locale,
                "pack_id": document.pack_id,
                "resolved_protocol_hash": document.resolved_protocol_hash,
                "entries": [
                    {
                        "text_hash": row.entry.text_hash,
                        "clip_id": row.entry.clip_id,
                        "voice": row.entry.voice,
                        "locale": row.entry.locale,
                        "text_tr": row.text_tr,
                        "scripted": row.scripted,
                        "subject": row.subject,
                    }
                    for row in clips
                ],
            }
        ),
    }
    artifacts[MANIFEST] = _dump(
        {
            "pack_id": document.pack_id,
            "version": document.version,
            "chain": list(document.chain),
            "overlays": list(document.overlays),
            "voice": voice,
            "locale": locale,
            "resolved_protocol_hash": document.resolved_protocol_hash,
            "opt_template_id": template.template_id,
            "opt_sha256": template.sha256,
            "artifacts": {
                name: hashlib.sha256(content.encode("utf-8")).hexdigest()
                for name, content in sorted(artifacts.items())
            },
        }
    )
    return CompiledBundle(
        pack_id=document.pack_id,
        version=document.version,
        voice=voice,
        locale=locale,
        resolved_protocol_hash=document.resolved_protocol_hash,
        opt_template_id=template.template_id,
        opt_sha256=template.sha256,
        clip_manifest=clips,
        artifacts=dict(sorted(artifacts.items())),
    )


def write_bundle(bundle: CompiledBundle, dist_root: Path) -> tuple[Path, ...]:
    """Write every artefact under ``<dist_root>/<pack_id>/``, sorted, then the
    signable ``bundle.tar.gz`` and its digest beside them (INT-058)."""
    target = dist_root / bundle.pack_id
    target.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, content in sorted(bundle.artifacts.items()):
        path = target / name
        path.write_text(content, encoding="utf-8")
        written.append(path)
    written.extend(write_archive(bundle, target))
    return tuple(written)
