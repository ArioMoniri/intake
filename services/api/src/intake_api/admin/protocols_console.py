"""The Protocols module's console composite (INT-565; files/08 §3; files/09 §1-4).

``GET /admin/protocols`` is the body ``apps/admin-web/src/protocols`` renders
(INT-184): the branch × maturity matrix, the proposal review queue and the
clip coverage per voice, computed at serve time from what the API already
serves.

- **The matrix** is ``protocols.taxonomy.coverage`` over the API's own
  validated taxonomy (``AppState.taxonomy``, the ``/v1/taxonomy`` feed) and
  the pack tree beside it. An L0 draft is named and never counted as coverage
  (invariant 13); a row that resolves names a servable pack.
- **The review queue** is proposal-only (invariant 12). Its vocabulary is
  Loop 2's, through :mod:`intake_platform.admin.console_vocab` — the API does
  not import ``intake_learning``. There is no persisted proposal store (the
  PR-bot opens PRs and a CODEOWNER clinician approves them), so the queue is
  empty and says so.
- **Clip coverage** is keyed by voice under the one spoken profile,
  ``residency_tr`` (``typed`` carries no clips ever, files/13 §13). Clips are
  pre-synthesised only for servable packs.

Ids, names from the taxonomy and counts only (invariant 6). :func:`protocols_payload`
is pure; ``scripts/dev/record_protocols_fixture.py`` records the e2e fixture
through it, so the fixture and the route cannot drift.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Final

from fastapi import Request
from fastapi.concurrency import run_in_threadpool
from intake_platform.admin import AdminRole, AdminWiring
from intake_platform.admin.console_vocab import EVIDENCE_CHECK_NAMES, PROPOSAL_TARGET_NAMES
from protocols.cli import load_registry
from protocols.loader import PackRegistry
from protocols.taxonomy import ResolutionStatus, Taxonomy, coverage, direct_pack_id

from intake_api.admin.console_sources import REPO
from intake_api.admin.deps import AdminCaller
from intake_api.errors import taxonomy_unconfigured
from intake_api.state import get_state

__all__ = ["protocols_payload", "protocols_read"]

#: The TTS voices under the one spoken profile (files/03 §4.9.1 rows 10-12).
_VOICES: Final = (
    ("voxcpm2-tts", "primary (cached-clip + dynamic, same voice_id)"),
    ("freya-tts", "session-start fallback"),
)

_QUEUE_SOURCE: Final = (
    "services/learning proposal PRs (INT-172): the PR-bot opens, a CODEOWNER clinician "
    "approves. This console records the review decision under 4-eyes and audits it; it "
    "never applies the protocol change itself (invariant 12)."
)


def _coverage(registry: PackRegistry, taxonomy: Taxonomy, source: str, day: str) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for row in coverage(registry, taxonomy):
        served = registry.maybe(row.pack_id) if row.pack_id is not None else None
        draft = registry.maybe(direct_pack_id(row.branch_id))
        rows.append(
            {
                "branch_id": row.branch_id,
                "name_tr": row.name_tr,
                "cluster": row.cluster,
                "status": row.status.value,
                "served_pack_id": row.pack_id,
                "served_maturity": served.maturity.value if served is not None else None,
                "draft_pack_id": draft.id if draft is not None else None,
                "draft_maturity": draft.maturity.value if draft is not None else None,
                "note": row.note,
            }
        )
    counts = Counter(row["status"] for row in rows)
    return {
        "generated_at": day,
        "taxonomy_source": source,
        "pack_count": len(registry),
        "summary": {
            "total": len(rows),
            **{status.value.lower(): counts.get(status.value, 0) for status in ResolutionStatus},
        },
        "rows": rows,
    }


def _clips(summary: dict[str, int], day: str) -> dict[str, Any]:
    return {
        "generated_at": day,
        "servable_pack_count": summary["direct"] + summary["cluster"],
        "note": (
            "clips are pre-synthesised per voice only for servable (L1+) packs "
            "(files/03 §4.9.1 row 10); every pack is L0 today, so no clip is required yet"
        ),
        "voices": [
            {
                "voice_id": voice,
                "profile": "residency_tr",
                "role": role,
                "required": 0,
                "cached": 0,
                "missing": 0,
                "missing_clips": [],
            }
            for voice, role in _VOICES
        ],
    }


def protocols_payload(
    *,
    registry: PackRegistry,
    taxonomy: Taxonomy,
    taxonomy_source: str,
    generated_at: datetime,
) -> dict[str, Any]:
    """The composite, from the pack tree and the taxonomy the caller loaded. Pure.

    Clip counts are zero only while no pack is servable; a servable pack has
    clips this module does not count, so it refuses rather than say zero.
    """
    day = generated_at.date().isoformat()
    matrix = _coverage(registry, taxonomy, taxonomy_source, day)
    if matrix["summary"]["direct"] + matrix["summary"]["cluster"] > 0:
        raise ValueError(
            "a servable pack exists, so clip coverage needs the clip manifest's counts; "
            "this composite does not read the manifest (invariant 17: never a zero it did "
            "not count)"
        )
    return {
        "coverage": matrix,
        "review_queue": {
            "source": _QUEUE_SOURCE,
            "allowed_targets": list(PROPOSAL_TARGET_NAMES),
            "unmet_check_names": list(EVIDENCE_CHECK_NAMES),
            "rows": [],
        },
        "clip_coverage": _clips(matrix["summary"], day),
    }


@lru_cache(maxsize=4)
def _registry(packs_root: Path) -> PackRegistry:
    # read once per root, like AppState.taxonomy: a changed tree is served
    # after a restart, never half-read mid-request
    return load_registry(packs_root)


async def protocols_read(
    request: Request, caller: AdminCaller, wiring: AdminWiring, role: AdminRole
) -> dict[str, Any]:
    state = get_state(request)
    loaded = state.taxonomy()
    if loaded is None:
        raise taxonomy_unconfigured()
    taxonomy_path = state.settings.taxonomy_path
    # the taxonomy lives at <packs root>/taxonomy/branches.yaml (files/09 §1)
    registry = await run_in_threadpool(_registry, taxonomy_path.parents[1])
    return protocols_payload(
        registry=registry,
        taxonomy=loaded.taxonomy,
        taxonomy_source=_repo_relative(taxonomy_path),
        generated_at=datetime.now(UTC),
    )


def _repo_relative(path: Path) -> str:
    """The source as the repository names it, never a host's filesystem layout."""
    try:
        return path.resolve().relative_to(REPO.resolve()).as_posix()
    except ValueError:
        return path.name
