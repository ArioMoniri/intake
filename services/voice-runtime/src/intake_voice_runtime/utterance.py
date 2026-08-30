"""Handing one answer to Layer B — the same way from either lane (INT-096).

``submit_utterance`` is one of the six tools and both lanes have it: the
Talker speaks the question, the typed lane displays it, and either way the
answer goes to the same per-session FIFO Work queue. The part that matters is
not the request shape but the check under it — files/12 §7.5 makes ``work_id``
**derived** from the content, so a restart re-submitting the same answer
resolves to the record that already exists instead of guaranteeing a duplicate.

That check lives here rather than in each lane because two copies of it are
two things that can drift, and the failure it guards against is silent: a
Layer B that minted an id instead of deriving one would look correct until the
first restart, and then double every answer it had already stored.
"""

from __future__ import annotations

import hashlib

from intake_voice_runtime.ports import WorkRequest, WorkSubmitter, WorkTicket, WorkType, work_key

__all__ = ["submit_extraction"]


def submit_extraction(
    backend: WorkSubmitter,
    *,
    session_id: str,
    step_id: str,
    transcript: str,
    protocol_hash: str,
    engine_version: int,
) -> WorkTicket:
    """Submit one answer as ``extract_slots`` Work and return at once.

    Nothing here awaits: :class:`~intake_voice_runtime.ports.WorkSubmitter`
    has no awaitable member (ADR-009), so there is no expression a lane could
    write that would wait on Backend Work.
    """
    request = WorkRequest(
        session_id=session_id,
        work_type=WorkType.EXTRACT_SLOTS,
        step_id=step_id,
        input_hash=hashlib.sha256(transcript.encode("utf-8")).hexdigest(),
        protocol_hash=protocol_hash,
        engine_version=engine_version,
    )
    ticket = backend.submit(request)
    if ticket.work_id != work_key(request):
        raise ValueError(
            "Layer B minted a work_id instead of deriving it; a restart would "
            "then duplicate every re-submitted transcript (files/12 §7.5)"
        )
    return ticket
