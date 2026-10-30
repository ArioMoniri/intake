"""INT-529 — the synthetic-scope legal index: texts for synthetic tenants only.

The owner's decision of 16 Oct 2026 ("for third do recommended", the INT-498
audit's proposal P6) lets the legal lane author consent and notice texts for
**synthetic tenants only**, so the synthetic host can exercise the consent flow
while the real-tenant index ``docs/legal/documents.yaml`` stays empty until a
licensed Turkish lawyer countersigns (HB-L27). This module is the loader for
that second index, and it is built so the two can never be confused:

- **A separate tree.** ``docs/legal/synthetic/`` holds its own
  ``documents.yaml``. Ids are the INT-210 aydınlatma and açık rıza ids, and each
  file path comes from :data:`~intake_platform.legal.documents.REQUIRED_DOCUMENTS`,
  never from the index, so an index row cannot point outside the tree.
- **A declared data class.** ``INTAKE_DEPLOYMENT_DATA_CLASS`` is read as
  ``synthetic`` only for that exact literal; everything else is ``real_phi``
  (ADR-035's own reader, reused). :class:`SyntheticLegalIndex` refuses
  to exist for any class but synthetic, and the index file must declare
  ``data_class: synthetic`` itself.
- **The bound data class (INT-536, INT-529 F8).** ADR-035 binds the class into
  the model-lane control record on the first control write, and a declaration
  that disagrees reads as ``real_phi``. Given the deployment's control store,
  every lookup reads the bound class fresh and refuses unless the effective
  class is synthetic. It also refuses when the record cannot be read, because
  then the class cannot be known. With no store configured nothing can be
  bound, so the declaration governs.
- **Hash binding as INT-210 does it.** Each row carries ``{version, sha256}``;
  the bytes must hash to the signed value and the front-matter version must
  equal the row's. Nothing is cached, so an edited file stops serving.
- **A visible marker.** The first line of every served body carries
  :data:`~intake_platform.consent.texts.SYNTHETIC_MARKER`. A text without it is
  refused, and the real-tenant catalog refuses any text with it.
- **Declared absence.** An id the lane could not ground in what the repository
  already declares is listed under ``awaiting_human`` with what is missing. It
  refuses as missing and names the gap; it is never filled with a guess.

Messages carry paths and ids only, never copy (invariant 6).
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import yaml

from intake_platform.consent.registry import resolve_scope
from intake_platform.consent.texts import (
    ConsentText,
    ConsentTextCatalog,
    ConsentTextInvalidError,
    ConsentTextMissingError,
    parse_text_file,
    synthetic_marker_is_visible,
)
from intake_platform.legal.claims import SCANNED_TREES, scan_text
from intake_platform.legal.documents import (
    REQUIRED_DOCUMENTS,
    DocumentKind,
    LegalDocumentError,
    LegalDocumentHashMismatchError,
    LegalDocumentInvalidError,
    LegalDocumentMissingError,
    UnknownLegalDocumentError,
    required_document,
)
from intake_platform.model_lanes.guard import ENV_DEPLOYMENT_DATA_CLASS, effective_data_class
from intake_platform.model_lanes.guard import deployment_data_class as deployment_data_class
from intake_platform.model_lanes.model import TenantDataClass
from intake_platform.model_lanes.store import ModelLanesReader, ModelLanesUnavailable

__all__ = [
    "DATA_CLASS_ENV",
    "SYNTHETIC_CONSENTS_ROOT",
    "SYNTHETIC_LEGAL_ROOT",
    "AwaitingHumanRow",
    "DeploymentDataClass",
    "SyntheticConsentTextCatalog",
    "SyntheticIndex",
    "SyntheticLegalIndex",
    "SyntheticLegalText",
    "SyntheticLegalTreeRefusedError",
    "SyntheticMarkerMissingError",
    "SyntheticRow",
    "deployment_data_class",
    "refuse_legal_paths_for",
    "synthetic_document_ids",
    "within_synthetic_legal_tree",
]

#: The declaration the synthetic image bakes (infra/staging/Dockerfile.api). One
#: reader for the whole deployment: ADR-035's guard (INT-428) reads the same
#: variable, so hosted lanes and synthetic legal texts can never disagree.
DATA_CLASS_ENV: Final[str] = ENV_DEPLOYMENT_DATA_CLASS
#: What a deployment holds — ADR-035's ``TenantDataClass``, under the name this
#: module's callers use.
DeploymentDataClass = TenantDataClass
SYNTHETIC_LEGAL_ROOT: Final[Path] = Path("docs/legal/synthetic")
SYNTHETIC_CONSENTS_ROOT: Final[Path] = SYNTHETIC_LEGAL_ROOT / "consents"
_INDEX_FILENAME: Final[str] = "documents.yaml"
_KINDS: Final = (DocumentKind.AYDINLATMA, DocumentKind.ACIK_RIZA)
_GROUNDS: Final = ("retention", "recipients", "categories", "bases")
_CLAIM_GROUPS: Final[tuple[str, ...]] = next(
    tree.groups for tree in SCANNED_TREES if tree.path == "docs/legal"
)


class SyntheticLegalTreeRefusedError(LegalDocumentError):
    """The synthetic tree was offered to a deployment that is not synthetic, a
    synthetic deployment was offered the real tree, or an index that does not
    declare itself synthetic was offered as the synthetic one."""


class SyntheticMarkerMissingError(LegalDocumentInvalidError):
    """A synthetic text whose first body line does not carry the marker."""


@dataclass(frozen=True)
class SyntheticRow:
    id: str
    version: str
    sha256: str
    grounds: Mapping[str, tuple[str, ...]]


@dataclass(frozen=True)
class AwaitingHumanRow:
    id: str
    missing: tuple[str, ...]
    ask: str
    refs: tuple[str, ...]


@dataclass(frozen=True)
class SyntheticIndex:
    version: str
    rows: Mapping[str, SyntheticRow]
    awaiting: Mapping[str, AwaitingHumanRow]


@dataclass(frozen=True)
class SyntheticLegalText:
    id: str
    kind: DocumentKind
    version: str
    text_hash: str
    path: Path
    body: str


def synthetic_document_ids() -> tuple[str, ...]:
    """The five aydınlatma and eleven açık rıza ids, in registry order."""
    return tuple(row.id for row in REQUIRED_DOCUMENTS if row.kind in _KINDS)


def within_synthetic_legal_tree(path: Path) -> bool:
    """Whether ``path`` (symlinks and ``..`` resolved) lies in a ``legal/synthetic``
    tree — the committed one or a copy of it, wherever it is mounted."""
    parts = Path(path).resolve(strict=False).parts
    return any(parts[i : i + 2] == ("legal", "synthetic") for i in range(len(parts) - 1))


def refuse_legal_paths_for(
    data_class: DeploymentDataClass, *, legal_root: Path, other_paths: Sequence[Path] = ()
) -> None:
    """Boot gate. A real deployment may not touch the synthetic tree with any of
    its legal paths; a synthetic one must take its consent texts from it."""
    if data_class is DeploymentDataClass.SYNTHETIC:
        if not within_synthetic_legal_tree(legal_root):
            raise SyntheticLegalTreeRefusedError(
                f"{DATA_CLASS_ENV}=synthetic binds synthetic texts only, and {legal_root} "
                "is not in a legal/synthetic tree (INT-529)"
            )
        return
    for path in (legal_root, *other_paths):
        if within_synthetic_legal_tree(path):
            raise SyntheticLegalTreeRefusedError(
                f"{path} is in the synthetic legal tree, which loads only when "
                f"{DATA_CLASS_ENV}=synthetic is baked into the image (INT-529)"
            )


def _strings(raw: object, *, where: str) -> tuple[str, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise LegalDocumentInvalidError(f"{where}: expected a list of strings")
    return tuple(item.strip() for item in raw)


def _text(raw: Mapping[str, Any], key: str, *, where: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise LegalDocumentInvalidError(f"{where}: {key!r} must be a non-empty string")
    return value.strip()


def _known(document_id: str, *, where: str) -> None:
    try:
        required = required_document(document_id)
    except UnknownLegalDocumentError as exc:
        raise LegalDocumentInvalidError(f"{where}: {exc}") from exc
    if required.kind not in _KINDS:
        raise LegalDocumentInvalidError(
            f"{where}: {document_id!r} is not an aydınlatma or açık rıza text; the synthetic "
            "index binds those sixteen ids only (INT-529)"
        )


def _row(raw: object, *, where: str) -> SyntheticRow:
    if not isinstance(raw, Mapping):
        raise LegalDocumentInvalidError(f"{where}: every documents entry must be a mapping")
    document_id = _text(raw, "id", where=where)
    _known(document_id, where=where)
    grounds_raw = raw.get("grounds") or {}
    if not isinstance(grounds_raw, Mapping):
        raise LegalDocumentInvalidError(f"{where}: {document_id!r} grounds must be a mapping")
    grounds = {key: _strings(grounds_raw.get(key), where=f"{where}:{key}") for key in _GROUNDS}
    return SyntheticRow(
        id=document_id,
        version=_text(raw, "version", where=where),
        sha256=_text(raw, "sha256", where=where),
        grounds=grounds,
    )


def _awaiting(raw: object, *, where: str) -> AwaitingHumanRow:
    if not isinstance(raw, Mapping):
        raise LegalDocumentInvalidError(f"{where}: every awaiting_human entry must be a mapping")
    document_id = _text(raw, "id", where=where)
    _known(document_id, where=where)
    missing = _strings(raw.get("missing"), where=f"{where}:{document_id}")
    if not missing or not all(missing):
        raise LegalDocumentInvalidError(f"{where}: {document_id!r} must name what is missing")
    return AwaitingHumanRow(
        id=document_id,
        missing=missing,
        ask=_text(raw, "ask", where=where),
        refs=_strings(raw.get("refs"), where=f"{where}:{document_id}"),
    )


class SyntheticLegalIndex:
    """Reads ``<root>/documents.yaml`` and the bytes it binds, fresh on every call."""

    def __init__(
        self,
        root: Path,
        *,
        data_class: DeploymentDataClass,
        bound: ModelLanesReader | None = None,
    ) -> None:
        if data_class is not DeploymentDataClass.SYNTHETIC:
            raise SyntheticLegalTreeRefusedError(
                f"the synthetic legal index loads only when {DATA_CLASS_ENV}=synthetic; "
                f"this deployment is {data_class.value} (INT-529)"
            )
        self._root = Path(root)
        self._declared = data_class
        self._bound = bound

    def _require_bound_synthetic(self) -> None:
        """ADR-035's bound class, read fresh on every lookup like the bytes
        (INT-536). Unreadable, or effectively ``real_phi``, refuses."""
        if self._bound is None:
            return
        try:
            bound = self._bound.read().data_class
        except ModelLanesUnavailable as exc:
            raise SyntheticLegalTreeRefusedError(
                f"the deployment's bound data class cannot be read ({exc.code}); the "
                "synthetic texts refuse until it can (ADR-035, INT-536)"
            ) from None
        effective = effective_data_class(self._declared, bound)
        if effective is not DeploymentDataClass.SYNTHETIC:
            named = bound.value if bound is not None else "unbound"
            raise SyntheticLegalTreeRefusedError(
                f"this deployment is bound {named} and so reads as {effective.value}; the "
                "synthetic texts load only where the bound class is synthetic (ADR-035, INT-536)"
            )

    @property
    def root(self) -> Path:
        return self._root

    def index(self) -> SyntheticIndex:
        path = self._root / _INDEX_FILENAME
        try:
            loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise LegalDocumentMissingError(f"no synthetic legal index at {path}") from exc
        except yaml.YAMLError as exc:
            raise LegalDocumentInvalidError(f"{path}: not valid YAML") from exc
        if not isinstance(loaded, Mapping):
            raise LegalDocumentInvalidError(f"{path}: the index must be a mapping")
        if loaded.get("data_class") != DeploymentDataClass.SYNTHETIC.value:
            raise SyntheticLegalTreeRefusedError(
                f"{path} does not declare data_class: synthetic, so it is not a synthetic index"
            )
        version = _text(loaded, "synthetic_index_version", where=str(path))
        rows: dict[str, SyntheticRow] = {}
        for entry in loaded.get("documents") or []:
            row = _row(entry, where=str(path))
            if row.id in rows:
                raise LegalDocumentInvalidError(f"{path}: {row.id!r} is declared twice")
            rows[row.id] = row
        awaiting: dict[str, AwaitingHumanRow] = {}
        for entry in loaded.get("awaiting_human") or []:
            gap = _awaiting(entry, where=str(path))
            if gap.id in awaiting or gap.id in rows:
                raise LegalDocumentInvalidError(
                    f"{path}: {gap.id!r} is declared twice — built and awaiting-human at once"
                )
            awaiting[gap.id] = gap
        return SyntheticIndex(version=version, rows=rows, awaiting=awaiting)

    def entry(self, document_id: str) -> SyntheticLegalText:
        """The servable synthetic text, or the one error that says why not."""
        self._require_bound_synthetic()
        required = required_document(document_id)
        _known(document_id, where=str(self._root))
        index = self.index()
        row = index.rows.get(document_id)
        if row is None:
            gap = index.awaiting.get(document_id)
            refs = f" ({', '.join(gap.refs)})" if gap is not None and gap.refs else ""
            state = "listed awaiting-human" if gap is not None else "not declared"
            raise LegalDocumentMissingError(
                f"{document_id!r} is {state} in the synthetic index{refs}; nothing renders"
            )
        path = self._root / required.relative_path
        try:
            raw = path.read_bytes()
        except FileNotFoundError as exc:
            raise LegalDocumentMissingError(
                f"no synthetic text for {document_id!r} at {path}"
            ) from exc
        digest = hashlib.sha256(raw).hexdigest()
        if digest != row.sha256:
            raise LegalDocumentHashMismatchError(
                f"{path}: the bytes hash to {digest} but the synthetic index signed {row.sha256}"
            )
        try:
            version, body = parse_text_file(path, raw)
        except ConsentTextInvalidError as exc:
            raise LegalDocumentInvalidError(str(exc)) from exc
        if version != row.version:
            raise LegalDocumentInvalidError(
                f"{path}: front-matter version {version!r} is not the indexed {row.version!r}"
            )
        if not synthetic_marker_is_visible(body):
            raise SyntheticMarkerMissingError(
                f"{path}: the first body line does not carry the sentetik test metni marker"
            )
        hits = scan_text(raw.decode("utf-8"), groups=_CLAIM_GROUPS, path=document_id)
        if hits:
            raise LegalDocumentInvalidError(
                f"{document_id}: carries a performance claim ({hits[0].pattern}, line "
                f"{hits[0].line_no}) — invariant 20"
            )
        return SyntheticLegalText(
            id=document_id,
            kind=required.kind,
            version=version,
            text_hash=digest,
            path=path,
            body=body,
        )

    def available(self) -> tuple[str, ...]:
        """The ids that resolve right now, in registry order."""
        out: list[str] = []
        for document_id in synthetic_document_ids():
            try:
                self.entry(document_id)
            except LegalDocumentError:
                continue
            out.append(document_id)
        return tuple(out)


class SyntheticConsentTextCatalog(ConsentTextCatalog):
    """The consent guard's catalog on a synthetic deployment.

    ``legal_root`` is the consents directory, as for the real catalog; the
    index sits in its parent. A scope resolves to its açık rıza id, and the
    text comes from :class:`SyntheticLegalIndex` — so the hash a grant binds is
    the one the synthetic index signs. Missing stays missing (``try_entry``
    answers ``None``); every other refusal is an invalid text and raises.
    """

    def __init__(
        self,
        legal_root: Path,
        *,
        data_class: DeploymentDataClass,
        bound: ModelLanesReader | None = None,
    ) -> None:
        super().__init__(legal_root)
        self._index = SyntheticLegalIndex(
            Path(legal_root).parent, data_class=data_class, bound=bound
        )

    def entry(self, scope: str) -> ConsentText:
        purpose = resolve_scope(scope).id
        document_id = "acik_riza." + purpose.replace(":", ".")
        try:
            text = self._index.entry(document_id)
        except LegalDocumentMissingError as exc:
            raise ConsentTextMissingError(str(exc)) from exc
        except LegalDocumentError as exc:
            raise ConsentTextInvalidError(str(exc)) from exc
        return ConsentText(
            purpose=purpose,
            version=text.version,
            text_hash=text.text_hash,
            path=text.path,
            body=text.body,
        )
