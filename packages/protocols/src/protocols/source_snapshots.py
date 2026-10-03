"""A source block checked against its committed snapshot (INT-465).

``dsl.SourceBlock`` requires the quote to appear verbatim in a committed snapshot.
Until INT-465 nothing checked that for a red-flag rule. The clinical review of #796
found the life-threat exemplars citing a URL the snapshot records as 404, a retrieval
date the snapshot does not carry, and quotes in a different case from the one EK-4
prints. This module is the one check, used by the life-threat loader
(``protocols.compile.life_threat``) and the generic RED loader
(``protocols.generic_red``):

- the snapshot path is repo-relative, under ``packages/protocols/sources/`` (or, for
  SENTETİK test sets only, ``tests/fixtures/protocols/sources/``), with no ``..``;
- the file exists, and its header declares the same ``guideline_id``;
- the quote appears verbatim in the body (NFC and whitespace runs only, as in the
  clinical decisions register);
- the url is the header's ``url`` or its ``url_annex``;
- ``retrieved_on`` is the header's ``retrieved_on``.

A snapshot is the record of what was retrieved, so a source block that disagrees with
it is refused rather than repaired.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from protocols.clinical_decisions import (
    DecisionRegisterError,
    quote_in_snapshot,
    snapshot_body,
    snapshot_header,
)

__all__ = ["SNAPSHOT_PREFIXES", "REPO_ROOT", "source_snapshot_problem"]

REPO_ROOT = Path(__file__).resolve().parents[4]
#: Where a committed snapshot may live. The second is for SENTETİK test sets only.
SNAPSHOT_PREFIXES = ("packages/protocols/sources/", "tests/fixtures/protocols/sources/")


def source_snapshot_problem(
    *,
    quote_snapshot: str,
    guideline_id: str,
    quote: str,
    url: str,
    retrieved_on: date,
    repo_root: Path | None = None,
) -> str | None:
    """Why this source disagrees with its snapshot, or ``None`` when it agrees."""
    if not quote_snapshot.startswith(SNAPSHOT_PREFIXES) or ".." in quote_snapshot:
        return f"snapshot {quote_snapshot!r} is not under {' or '.join(SNAPSHOT_PREFIXES)}"
    path = (repo_root if repo_root is not None else REPO_ROOT) / quote_snapshot
    try:
        text = path.read_text(encoding="utf-8")
        header, body = snapshot_header(text), snapshot_body(text)
    except (OSError, UnicodeDecodeError, DecisionRegisterError):
        return f"snapshot {quote_snapshot!r} is not committed, or has no header"
    if header.get("guideline_id") != guideline_id:
        return f"snapshot {quote_snapshot!r} is not {guideline_id}"
    if not quote_in_snapshot(quote, body):
        return f"the quote is not verbatim in {quote_snapshot!r}"
    if url not in {header.get("url"), header.get("url_annex")}:
        return f"the url is neither the url nor the url_annex of {quote_snapshot!r}"
    if retrieved_on.isoformat() != header.get("retrieved_on"):
        return f"retrieved_on is not the retrieval date of {quote_snapshot!r}"
    return None
