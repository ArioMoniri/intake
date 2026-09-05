"""INT-320 (follow-up) — the embed launch's consent document set (ADR-029).

The launch resolves a ``consent_doc_set_id``; this is the step that turns that
id into the hash-bound consent documents the branded intake must show before a
single clinical turn. Two documents make the dev set:

- ``core`` — the standard service consent, loaded from the SAME global catalog
  a later ``POST /v1/consents/grant`` binds against, so what the patient is
  shown and what a grant records can never drift apart (files/06 §2);
- ``partner_processor`` — the partner-processor disclosure (aydınlatma, not a
  grantable açık rıza), loaded from the tenant's own ``legal_root`` so a
  partner's processing statement is per-tenant.

Fail closed like the rest of the legal flow (invariant 18): if EITHER document
is absent the set is empty, and an empty set is what the API turns into a 503 —
never a launch that shows the patient nothing.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from intake_platform.consent import ConsentTextCatalog
from intake_platform.consent.texts import (
    ConsentTextInvalidError,
    bind_legal_document,
)
from intake_platform.embed import (
    embed_disclosure_root,
    resolve_embed_consent_documents,
)

_CORE = """---
consent_text_version: v1-demo.1
---
Temel hizmet

Muayeneden önce şikâyetlerinizi toplar ve hekiminize düzenli bir ön not iletiriz.
"""

_DISCLOSURE = """---
consent_text_version: v1-demo.1
---
Ortak üzerinden giriş

Bu ön görüşmeyi ortağınız üzerinden başlattınız. Verileriniz, ortağınız adına
Vizite tarafından işlenir.
"""

DOC_SET = "embed.dev-partner-alpha"


def _author(root: Path, name: str, body: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / name
    path.write_text(body, encoding="utf-8")
    return path


def test_disclosure_root_swaps_the_docs_legal_prefix_for_the_dev_base() -> None:
    # prod: the repo's docs/legal tree; dev: the ~/.config/intake/dev-legal tree
    assert embed_disclosure_root("docs/legal/embed/dev-partner-alpha", Path("docs/legal")) == Path(
        "docs/legal/embed/dev-partner-alpha"
    )
    assert embed_disclosure_root(
        "docs/legal/embed/dev-partner-alpha", Path("/home/dev/.config/intake/dev-legal")
    ) == Path("/home/dev/.config/intake/dev-legal/embed/dev-partner-alpha")


def test_bind_legal_document_is_hash_bound_over_the_whole_file(tmp_path: Path) -> None:
    path = _author(tmp_path, "partner_processor.tr.md", _DISCLOSURE)
    bound = bind_legal_document(path)
    assert bound.version == "v1-demo.1"
    assert "Vizite tarafından işlenir" in bound.body
    assert len(bound.text_hash) == 64
    # a byte changed anywhere re-binds the hash (version + copy can never drift)
    path.write_text(_DISCLOSURE + "\n", encoding="utf-8")
    assert bind_legal_document(path).text_hash != bound.text_hash


def test_bind_legal_document_rejects_an_unversioned_file(tmp_path: Path) -> None:
    path = _author(tmp_path, "bad.tr.md", "no front matter here")
    with pytest.raises(ConsentTextInvalidError):
        bind_legal_document(path)


def test_full_doc_set_renders_core_and_the_disclosure(tmp_path: Path) -> None:
    global_root = tmp_path / "consents"
    disclosure_root = tmp_path / "embed" / "dev-partner-alpha"
    _author(global_root, "core.tr.md", _CORE)
    _author(disclosure_root, "partner_processor.tr.md", _DISCLOSURE)

    doc_set = resolve_embed_consent_documents(
        doc_set_id=DOC_SET,
        consent_catalog=ConsentTextCatalog(global_root),
        disclosure_root=disclosure_root,
    )
    assert doc_set.doc_set_id == DOC_SET
    by_id = {d.doc_id: d for d in doc_set.documents}
    # the core doc is grantable and carries the scope the ledger records against
    assert by_id["core"].kind == "consent"
    assert by_id["core"].grant_scope == "core"
    assert by_id["core"].version == "v1-demo.1"
    # the disclosure is shown, never granted
    assert by_id["partner_processor"].kind == "disclosure"
    assert by_id["partner_processor"].grant_scope is None
    assert "işlenir" in by_id["partner_processor"].body


def test_missing_disclosure_fails_closed_to_an_empty_set(tmp_path: Path) -> None:
    global_root = tmp_path / "consents"
    disclosure_root = tmp_path / "embed" / "dev-partner-alpha"
    _author(global_root, "core.tr.md", _CORE)
    # the tenant's disclosure is NOT authored — the pre-sign-off state (HB-L27)

    doc_set = resolve_embed_consent_documents(
        doc_set_id=DOC_SET,
        consent_catalog=ConsentTextCatalog(global_root),
        disclosure_root=disclosure_root,
    )
    assert doc_set.documents == ()


def test_missing_core_fails_closed_to_an_empty_set(tmp_path: Path) -> None:
    global_root = tmp_path / "consents"
    disclosure_root = tmp_path / "embed" / "dev-partner-alpha"
    # core absent (the global legal tree unauthored); disclosure present
    _author(disclosure_root, "partner_processor.tr.md", _DISCLOSURE)

    doc_set = resolve_embed_consent_documents(
        doc_set_id=DOC_SET,
        consent_catalog=ConsentTextCatalog(global_root),
        disclosure_root=disclosure_root,
    )
    assert doc_set.documents == ()
