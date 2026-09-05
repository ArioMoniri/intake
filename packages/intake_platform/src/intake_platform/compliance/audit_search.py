"""Ids/codes-only search over administrative audit rows (INT-189).

files/08 §4 gives the Compliance module an "audit-log search". Two boundaries
make it safe to build:

- **It surfaces administrative actions only.** "Who read this patient's note"
  is answered by the governed break-glass ceremony and the patient access-log
  (INT-016, files/08 §2.5), and HB-L6 is precisely the finding that patient
  content had four *unmanaged* read paths collapsed into one audited one. A
  compliance search that returned patient-content-access rows would be a fifth
  such path, so it does not: only ``admin.*`` rows are in scope, and a query
  aimed at patient content is refused rather than emptied.
- **It never returns content or chain material.** The projection is a closed,
  id-shaped field set (the same discipline as INT-016's ``AccessLogRow``) with
  no ``entry_hash``/``prev_hash`` — the console sits inside the
  ``platform_admin`` blast radius and must not hold chain material it could
  recompute a head from (HB-I12, files/08 §0c F5). A candidate row whose
  reference is not id-shaped is refused, not painted.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from intake_platform.audit import AuditEntry

__all__ = [
    "ADMIN_ACTION_PREFIX",
    "AuditSearchContentRefused",
    "AuditSearchQuery",
    "AuditSearchRow",
    "search_audit",
]

#: Only administrative actions are in scope (see the module docstring).
ADMIN_ACTION_PREFIX: Final = "admin."

#: The id shape a filter value and a rendered reference must both hold: an
#: identifier or a dotted/colon code, never prose. Free text (a space, a
#: comma) fails it, which is how a content-shaped value is caught at the door.
_ID_SHAPE: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,127}$")


class AuditSearchContentRefused(Exception):
    """The search would return content, or was asked to reach patient content.

    ``code`` is a stable machine code — a refusal reaches an HTTP body and a
    metric label, and narrative in either is how PHI travels (invariant 6).
    """

    code = "audit_search_content_refused"


@dataclass(frozen=True)
class AuditSearchRow:
    """One search hit, ids only.

    No hash — the console must not hold chain material (HB-I12) — and no
    ``resource_ref`` either: for an administrative row it is
    ``admin_action:<correlation>:<content-digest>``, whose 64-hex digest is not
    chain material but is indistinguishable from it to the "no hash leaves the
    console" guard, and it is opaque to a reader anyway. The action name is the
    semantic ("who did what, when"); the digest is not.
    """

    seq: int
    occurred_at_utc: str
    actor: str
    action: str


@dataclass(frozen=True)
class AuditSearchQuery:
    """A filter over administrative rows. Every value is id-shaped or the
    query is refused before it touches the log."""

    action_prefix: str | None = None
    actor: str | None = None
    since: str | None = None
    until: str | None = None

    def __post_init__(self) -> None:
        for name in ("action_prefix", "actor"):
            value = getattr(self, name)
            if value is not None and not _ID_SHAPE.match(value):
                raise AuditSearchContentRefused(
                    f"{name} must be an identifier, not free text (invariant 6)"
                )
        # an action_prefix that aims outside the administrative family would
        # reach patient-content-access rows — refused, not silently emptied
        if self.action_prefix is not None and not self.action_prefix.startswith(
            ADMIN_ACTION_PREFIX.rstrip(".")
        ):
            raise AuditSearchContentRefused(
                "the compliance audit search covers administrative actions only; "
                "patient-content access is answered by the break-glass access log (HB-L6)"
            )


def _is_administrative(entry: AuditEntry) -> bool:
    return entry.action.startswith(ADMIN_ACTION_PREFIX)


def search_audit(
    entries: Sequence[AuditEntry], *, query: AuditSearchQuery
) -> tuple[AuditSearchRow, ...]:
    """Project the administrative rows that match ``query`` into id-only hits.

    Non-administrative rows are never in scope. A matching row whose actor or
    resource reference is not id-shaped is refused rather than rendered, so a
    content-shaped value can never reach the response even if it reached the
    chain.
    """
    hits: list[AuditSearchRow] = []
    for entry in entries:
        if not _is_administrative(entry):
            continue
        if query.action_prefix is not None and not entry.action.startswith(query.action_prefix):
            continue
        if query.actor is not None and entry.actor != query.actor:
            continue
        if query.since is not None and entry.timestamp_utc < query.since:
            continue
        if query.until is not None and entry.timestamp_utc > query.until:
            continue
        if not _ID_SHAPE.match(entry.actor) or not _ID_SHAPE.match(entry.resource_ref):
            # even though resource_ref is not rendered, a non-id-shaped one on a
            # matched row means the chain took content it should not have —
            # refuse the whole search rather than serve alongside it (invariant 6)
            raise AuditSearchContentRefused(
                "an audit row carried a non-id-shaped reference; refusing to render it "
                "(invariant 6)"
            )
        hits.append(
            AuditSearchRow(
                seq=entry.seq,
                occurred_at_utc=entry.timestamp_utc,
                actor=entry.actor,
                action=entry.action,
            )
        )
    hits.sort(key=lambda row: row.seq)
    return tuple(hits)
