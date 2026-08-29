"""Document endpoints over the INT-034 store (INT-197 dev-tier slice).

Flow, matching the INT-034 posture exactly:

- ``POST …/documents`` mints a presigned upload slot — the object lands
  under ``quarantine/`` and a ``documents`` row records the DECLARED sha256
  as unverified provenance (the client's claim is data, not truth);
- ``PUT …/documents/{id}/content`` is the dev-tier scan pass: the bytes run
  the full :meth:`DocumentStore.put_document` pipeline (server-side digest,
  AV hook, quarantine→clean promotion). Without a wired scanner it fails
  closed (503); INFECTED is retained under ``infected/`` and never served.
  The INT-120 ClamAV worker replaces this in-request pass for presigned
  uploads;
- ``GET …/documents/{id}/url`` mints a short-TTL download URL for
  scanned-clean documents only (409 before the scan pass).

No filename crosses this API in any direction (invariant 6). All routes are
patient-only in this slice — document sharing to the clinic side is its own
consented flow (share:*), not built here. Every route checks the patient's
``documents`` consent scope and appends to the hash-chained audit log
(invariant 4); the INT-034 store's own audit entries ride the SAME chain,
serialised by :class:`intake_api.audit.AuditWriter`.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from intake_platform.audit import AuditChain
from intake_platform.documents import (
    ALLOWED_CONTENT_TYPES,
    DEFAULT_PRESIGN_TTL,
    ContentTypeNotAllowedError,
    DigestMismatchError,
    DocumentRef,
    DocumentRejectedError,
    DocumentState,
    DocumentStore,
    DocumentTooLargeError,
    NoScanConfiguredError,
    ObjectStorageClient,
    PresignedUpload,
    Scanner,
)
from intake_platform.uploads import ScanFailedError
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from intake_api import store
from intake_api.audit import AuditWriter
from intake_api.auth import Principal, require_patient
from intake_api.consent_guard import require_scopes
from intake_api.db import tenant_session
from intake_api.dev_fixture import DevAccount
from intake_api.errors import not_found
from intake_api.state import ApiState, State

__all__ = ["DocumentsConfig", "DocumentsGateway", "router"]

router = APIRouter(prefix="/v1/visits/{visit_id}/documents", tags=["documents"])

DOCUMENTS_SCOPE = "documents"

_SHA256_SHAPE = re.compile(r"[0-9a-f]{64}")
_PRESIGN_TTL_S = int(DEFAULT_PRESIGN_TTL.total_seconds())

DocState = Literal["quarantined", "clean", "rejected"]


@dataclass
class DocumentsConfig:
    """The INT-034 seams the API wires at boot: object-storage client,
    bucket pair, and the AV hook (None = fail closed on ingest)."""

    client: ObjectStorageClient
    bucket_docs: str
    bucket_audit: str
    scanner: Scanner | None
    actor: str = "svc-api-documents"


class DocumentsGateway:
    """Runs INT-034 DocumentStore operations through the shared audit lock —
    the store appends to the same hash chain as the API's own entries, and
    two writers with private heads would fork it (invariant 4)."""

    def __init__(self, config: DocumentsConfig, audit: AuditWriter) -> None:
        self._config = config
        self._audit = audit
        self._buckets_ready = False

    @property
    def bucket_docs(self) -> str:
        return self._config.bucket_docs

    def _store(self, chain: AuditChain) -> DocumentStore:
        return DocumentStore(
            self._config.client,
            self._config.bucket_docs,
            self._config.bucket_audit,
            chain,
            scanner=self._config.scanner,
            actor=self._config.actor,
        )

    async def presigned_upload(
        self, *, tenant_id: uuid.UUID, patient_ref: str, consent_scope_ref: str
    ) -> PresignedUpload:
        def _mint(chain: AuditChain) -> PresignedUpload:
            doc_store = self._ready_store(chain)
            return doc_store.presigned_put(
                str(tenant_id), patient_ref, consent_scope_ref=consent_scope_ref
            )

        return await self._audit.run_locked(_mint)

    async def ingest(
        self,
        *,
        tenant_id: uuid.UUID,
        patient_ref: str,
        file_bytes: bytes,
        content_type: str,
        sha256: str,
        consent_scope_ref: str,
    ) -> DocumentRef:
        def _put(chain: AuditChain) -> DocumentRef:
            doc_store = self._ready_store(chain)
            return doc_store.put_document(
                str(tenant_id),
                patient_ref,
                file_bytes,
                content_type,
                sha256,
                consent_scope_ref=consent_scope_ref,
            )

        return await self._audit.run_locked(_put)

    async def download_url(self, *, ref: DocumentRef, consent_scope_ref: str) -> str:
        def _sign(chain: AuditChain) -> str:
            doc_store = self._ready_store(chain)
            return doc_store.presigned_get(ref, consent_scope_ref=consent_scope_ref)

        return await self._audit.run_locked(_sign)

    def _ready_store(self, chain: AuditChain) -> DocumentStore:
        doc_store = self._store(chain)
        if not self._buckets_ready:
            doc_store.ensure_buckets()
            self._buckets_ready = True
        return doc_store


# --- request/response bodies -------------------------------------------------------------


class DocumentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_type: str = Field(max_length=100)
    sha256: str = Field(max_length=64)


class DocumentSlotOut(BaseModel):
    id: uuid.UUID
    state: DocState
    content_type: str
    sha256: str
    upload_url: str
    expires_s: int


class DocumentOut(BaseModel):
    id: uuid.UUID
    state: DocState
    content_type: str
    sha256: str
    created_at: str


class DocumentIngestOut(BaseModel):
    id: uuid.UUID
    state: DocState
    sha256: str


class DownloadUrlOut(BaseModel):
    url: str
    expires_s: int


# --- helpers -------------------------------------------------------------------------------


def _doc_state(row_provenance: dict[str, object]) -> DocState:
    state = row_provenance.get("state")
    if state == "clean":
        return "clean"
    if state == "rejected":
        return "rejected"
    return "quarantined"


async def _own_visit_or_404(
    session: AsyncSession, principal: DevAccount, visit_id: uuid.UUID
) -> store.VisitRecord:
    record = await store.get_visit(
        session,
        tenant_id=principal.tenant_id,
        visit_id=visit_id,
        patient_id=principal.patient_id,
    )
    if record is None:
        raise not_found()
    return record


def _gateway(state: ApiState) -> DocumentsGateway:
    if state.documents is None:
        raise HTTPException(status_code=503, detail={"error": "documents_unconfigured"})
    return state.documents


async def _patient_pseudonym(
    session: AsyncSession, *, tenant_id: uuid.UUID, patient_id: uuid.UUID
) -> str:
    """What addresses this patient in object storage: the patients row's own
    Tokenizer pseudonym (INT-228).

    Until INT-228 this seam passed ``patient_id.hex`` instead, because a real
    pseudonym (``kid.`` + 64 hex) did not fit the store's 40-character key
    segment. It fits now — the store derives a fixed-width segment from
    whatever token it is handed — so the workaround is gone and the row's own
    pseudonym is what travels.

    An absent row is a refusal, not a fallback. The alternative would be
    reaching for the row id again, and a value invented to keep a request
    moving is exactly what invariant 14 forbids.
    """
    pseudonym = await store.get_patient_pseudonym(
        session, tenant_id=tenant_id, patient_id=patient_id
    )
    if pseudonym is None:
        raise HTTPException(status_code=503, detail={"error": "patient_unresolved"})
    return pseudonym


# --- endpoints -------------------------------------------------------------------------------


@router.post(
    "",
    response_model=DocumentSlotOut,
    status_code=201,
    dependencies=[require_scopes(DOCUMENTS_SCOPE)],
)
async def mint_upload_slot(
    visit_id: uuid.UUID, payload: DocumentCreate, principal: Principal, state: State
) -> DocumentSlotOut:
    patient, patient_id = require_patient(principal)
    gateway = _gateway(state)
    if payload.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=422, detail={"error": "content_type_not_allowed"})
    sha256 = payload.sha256.lower()
    if not _SHA256_SHAPE.fullmatch(sha256):
        raise HTTPException(status_code=422, detail={"error": "bad_sha256"})

    async with tenant_session(state.engine, patient.tenant_id) as session:
        await _own_visit_or_404(session, patient, visit_id)
        slot = await gateway.presigned_upload(
            tenant_id=patient.tenant_id,
            patient_ref=await _patient_pseudonym(
                session, tenant_id=patient.tenant_id, patient_id=patient_id
            ),
            consent_scope_ref=f"scope:{DOCUMENTS_SCOPE}",
        )
        row = await store.create_document_row(
            session,
            tenant_id=patient.tenant_id,
            patient_id=patient_id,
            visit_id=visit_id,
            object_ref=f"{gateway.bucket_docs}/{slot.key}",
            sha256=sha256,
            media_type=payload.content_type,
            provenance={
                "channel": "presigned-put",
                "state": "quarantined",
                "sha256_verified": False,
                "store_document_id": slot.document_id,
            },
        )
        await state.audit.record(
            actor=patient.account_id,
            action="api.document.create",
            resource_ref=f"doc:{row.id}",
            consent_scope=f"scope:{DOCUMENTS_SCOPE}",
        )
        return DocumentSlotOut(
            id=row.id,
            state="quarantined",
            content_type=payload.content_type,
            sha256=sha256,
            upload_url=slot.url,
            expires_s=_PRESIGN_TTL_S,
        )


@router.get("", response_model=list[DocumentOut], dependencies=[require_scopes(DOCUMENTS_SCOPE)])
async def list_documents(
    visit_id: uuid.UUID, principal: Principal, state: State
) -> list[DocumentOut]:
    patient, patient_id = require_patient(principal)
    async with tenant_session(state.engine, patient.tenant_id) as session:
        await _own_visit_or_404(session, patient, visit_id)
        rows = await store.list_document_rows(
            session, tenant_id=patient.tenant_id, visit_id=visit_id
        )
        await state.audit.record(
            actor=patient.account_id,
            action="api.document.list",
            resource_ref=f"visit:{visit_id}",
            consent_scope=f"scope:{DOCUMENTS_SCOPE}",
        )
        return [
            DocumentOut(
                id=row.id,
                state=_doc_state(dict(row.provenance)),
                content_type=row.media_type,
                sha256=row.sha256,
                created_at=row.created_at.isoformat(),
            )
            for row in rows
        ]


@router.put(
    "/{doc_id}/content",
    response_model=DocumentIngestOut,
    dependencies=[require_scopes(DOCUMENTS_SCOPE)],
)
async def ingest_content(
    visit_id: uuid.UUID, doc_id: uuid.UUID, request: Request, principal: Principal, state: State
) -> DocumentIngestOut:
    patient, patient_id = require_patient(principal)
    gateway = _gateway(state)
    file_bytes = await request.body()
    content_type = request.headers.get("content-type", "")

    result: DocumentIngestOut | None = None
    async with tenant_session(state.engine, patient.tenant_id) as session:
        await _own_visit_or_404(session, patient, visit_id)
        row = await store.get_document_row(
            session, tenant_id=patient.tenant_id, visit_id=visit_id, doc_id=doc_id
        )
        if row is None:
            raise not_found()
        if content_type != row.media_type:
            raise HTTPException(status_code=422, detail={"error": "content_type_mismatch"})

        pseudonym = await _patient_pseudonym(
            session, tenant_id=patient.tenant_id, patient_id=patient_id
        )
        try:
            ref = await gateway.ingest(
                tenant_id=patient.tenant_id,
                patient_ref=pseudonym,
                file_bytes=file_bytes,
                content_type=content_type,
                sha256=row.sha256,
                consent_scope_ref=f"scope:{DOCUMENTS_SCOPE}",
            )
        except DocumentTooLargeError:
            raise HTTPException(status_code=413, detail={"error": "too_large"}) from None
        except ContentTypeNotAllowedError:
            raise HTTPException(
                status_code=422, detail={"error": "content_type_not_allowed"}
            ) from None
        except DigestMismatchError:
            raise HTTPException(status_code=422, detail={"error": "digest_mismatch"}) from None
        except NoScanConfiguredError:
            raise HTTPException(status_code=503, detail={"error": "scan_not_configured"}) from None
        except ScanFailedError:
            # A scanner IS wired but produced no verdict — clamd unreachable,
            # timed out, ERROR reply, stream cut. That is a scan failure, not
            # a server fault: the row stays quarantined (never promoted, never
            # fetchable) and the client gets a code it can word honestly.
            raise HTTPException(status_code=503, detail={"error": "scan_failed"}) from None
        except DocumentRejectedError:
            # the rejected state must COMMIT (raising here would roll it
            # back); the HTTP refusal is raised after the session closes.
            # The store has already audited document.rejected on the chain.
            provenance = dict(row.provenance)
            provenance.update({"state": "rejected", "sha256_verified": True})
            await store.update_document_row(session, row, provenance=provenance)
        else:
            provenance = dict(row.provenance)
            provenance.update(
                {
                    "state": "clean",
                    "sha256_verified": True,
                    "clean_document_id": ref.document_id,
                    "size_bytes": ref.size_bytes,
                }
            )
            await store.update_document_row(
                session,
                row,
                object_ref=f"{ref.bucket}/{ref.key}",
                sha256=ref.sha256,
                provenance=provenance,
            )
            await state.audit.record(
                actor=patient.account_id,
                action="api.document.ingest",
                resource_ref=f"doc:{row.id}",
                consent_scope=f"scope:{DOCUMENTS_SCOPE}",
            )
            result = DocumentIngestOut(id=row.id, state="clean", sha256=ref.sha256)
    if result is None:
        raise HTTPException(status_code=422, detail={"error": "document_rejected"})
    return result


@router.get(
    "/{doc_id}/url",
    response_model=DownloadUrlOut,
    dependencies=[require_scopes(DOCUMENTS_SCOPE)],
)
async def download_url(
    visit_id: uuid.UUID, doc_id: uuid.UUID, principal: Principal, state: State
) -> DownloadUrlOut:
    patient, patient_id = require_patient(principal)
    gateway = _gateway(state)
    async with tenant_session(state.engine, patient.tenant_id) as session:
        await _own_visit_or_404(session, patient, visit_id)
        row = await store.get_document_row(
            session, tenant_id=patient.tenant_id, visit_id=visit_id, doc_id=doc_id
        )
        if row is None:
            raise not_found()
        provenance = dict(row.provenance)
        if _doc_state(provenance) != "clean":
            raise HTTPException(status_code=409, detail={"error": "document_not_scanned"})

        # The key is READ from the row, never recomputed. That is what keeps
        # objects stored under an older key shape reachable: the derivation
        # that produced a key belongs to the moment of writing, and the row is
        # the record of it (pinned by
        # test_a_document_written_under_the_old_key_shape_is_still_downloadable).
        bucket, _, key = row.object_ref.partition("/")
        size = provenance.get("size_bytes")
        ref = DocumentRef(
            tenant_id=str(patient.tenant_id),
            patient_pseudonym=await _patient_pseudonym(
                session, tenant_id=patient.tenant_id, patient_id=patient_id
            ),
            document_id=str(provenance.get("clean_document_id", row.id.hex)),
            bucket=bucket,
            key=key,
            content_type=row.media_type,
            size_bytes=size if isinstance(size, int) else 0,
            sha256=row.sha256,
            state=DocumentState.CLEAN,
        )
        url = await gateway.download_url(ref=ref, consent_scope_ref=f"scope:{DOCUMENTS_SCOPE}")
        await state.audit.record(
            actor=patient.account_id,
            action="api.document.download",
            resource_ref=f"doc:{row.id}",
            consent_scope=f"scope:{DOCUMENTS_SCOPE}",
        )
        return DownloadUrlOut(url=url, expires_s=_PRESIGN_TTL_S)
