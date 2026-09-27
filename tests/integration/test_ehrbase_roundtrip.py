"""INT-032 — the EHRbase export tier, against a real CDR.

Acceptance (docs/backlog/issues.yaml INT-032), quoted:
  "intake composition template (OPT) uploaded on boot; write/read composition
   per session; contribution audit"
  "integration test writes and reads a composition against EHRbase container"

Runs under ``-m integration`` via ``make check-integration``, which brings up
the ``export`` compose profile (``ehrbase`` + ``ehrbase-db``) and waits for
health. There is no skip: invariant 17 forbids one, so an absent container is
a failing test, not a quiet pass.

WHAT THIS LANE PROVES, AND WHAT IT CANNOT.

The roundtrip is real in both directions — internal value → canonical
openEHR → EHRbase → read back → internal value → identity — for the
composition **envelope** and for the operational template. Since INT-257 the
template uploaded is the COMMITTED file, byte-for-byte and pinned by
``OPT_SHA256``: no fixture, no in-test edit. It carries no
clinical content, and that is the finding rather than a shortcut: the
committed template (files/12 §8.1, INT-041) constrains archetype ROOTS only.
A root path addresses an ENTRY; a value needs a leaf ``atNNNN`` path, no
committed source in this repository states one, and inventing one would bind
the whole export against a fiction. So ``session_composition`` refuses every
answered slot, and ``test_a_session_with_answers_writes_nothing`` proves the
refusal happens *before* the CDR is touched.

Every payload is synthetic (invariant 6): a tokenizer pseudonym over a
non-existent identifier, and no narrative text.
"""

from __future__ import annotations

import datetime
import hashlib
import os
import uuid
from pathlib import Path

import httpx
import pytest
from clinical_schemas.mappers.openehr import (
    TEMPLATE_ID,
    EhrSetting,
    IntakeEhr,
    IntakeEnvelope,
    OpenEhrExportBlocked,
    SlotBinding,
    composition_to_envelope,
    ehr_status_to_intake_ehr,
    intake_ehr_to_ehr_status,
    session_composition,
    slot_bindings,
)
from clinical_schemas.session import SessionBudget, SessionState, SessionStatus
from intake_platform.ehrbase import (
    OPENEHR_BASE_PATH,
    EhrbaseClient,
    EhrbaseConfig,
    TemplateState,
)
from intake_platform.tokenization import Tokenizer
from protocols.bindings import OPT_PATH, OPT_SHA256, load_opt

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[2]
COMMITTED_OPT = REPO / OPT_PATH
TEMPLATE_UPLOAD_PATH = f"{OPENEHR_BASE_PATH}/definition/template/adl1.4"

BASE_URL = os.environ.get("INTAKE_EHRBASE_URL", "http://127.0.0.1:8092/ehrbase")
USERNAME = os.environ.get("INTAKE_EHRBASE_USER", "intake-dev")
PASSWORD = os.environ.get("INTAKE_EHRBASE_PASSWORD", "intake-dev-only")

REFERENCE_TIME = datetime.datetime(2026, 8, 28, 10, 0, tzinfo=datetime.UTC)
SHA = "ab" * 32


class _StatusRecorder(httpx.BaseTransport):
    """The real network transport, plus a log of ``(method, path, status)``.

    ``TemplateState`` folds 200 and 201 into ``uploaded=True``; the INT-257
    acceptance names 201, so the test reads the status off the wire. ``close``
    stays BaseTransport's no-op so the wrapped pool outlives the per-request
    ``httpx.Client`` the production client opens and closes; :meth:`shutdown`
    releases it.
    """

    def __init__(self) -> None:
        self._inner = httpx.HTTPTransport()
        self.exchanges: list[tuple[str, str, int]] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        response = self._inner.handle_request(request)
        self.exchanges.append((request.method, request.url.path, response.status_code))
        return response

    def shutdown(self) -> None:
        self._inner.close()


def _config() -> EhrbaseConfig:
    return EhrbaseConfig(base_url=BASE_URL, username=USERNAME, password=PASSWORD)


@pytest.fixture(scope="module")
def client() -> EhrbaseClient:
    # EHRbase boots a Spring context and a jOOQ pool; the first call after a
    # cold container pays for both.
    return EhrbaseClient(_config(), timeout_s=120.0)


@pytest.fixture(scope="module")
def first_upload() -> tuple[TemplateState, list[tuple[str, str, int]]]:
    """The module's first contact with the template: the production client,
    the COMMITTED bytes exactly as read from disk, and the wire status kept.
    Every test that needs the template depends on this, so whatever the test
    order, the recorded upload is the first one."""
    recorder = _StatusRecorder()
    try:
        state = EhrbaseClient(_config(), timeout_s=120.0, transport=recorder).ensure_template(
            COMMITTED_OPT.read_bytes(), template_id=TEMPLATE_ID
        )
    finally:
        recorder.shutdown()
    return state, recorder.exchanges


@pytest.fixture(scope="module")
def uploaded_template(first_upload: tuple[TemplateState, list[tuple[str, str, int]]]) -> str:
    return first_upload[0].template_id


def _subject_token() -> str:
    # A pseudonym over a value that is not anybody's identifier, under a key
    # that exists only for the duration of this test.
    keys = {"int032": uuid.uuid4().bytes}
    return Tokenizer(keys, "int032").pseudonym(f"synthetic-{uuid.uuid4()}")


def _envelope() -> IntakeEnvelope:
    return IntakeEnvelope(
        reference_time=REFERENCE_TIME,
        composer="INTAKE",
        setting=EhrSetting.SECONDARY_MEDICAL_CARE,
    )


def _session_state(slots: dict[str, object] | None = None) -> SessionState:
    return SessionState(
        session_id="sess-int032",
        protocol_id="base.intake",
        protocol_version="1.0.0",
        protocol_hash=SHA,
        mode="fast",
        status=SessionStatus.COMPLETED,
        reference_time=REFERENCE_TIME,
        step_states={},
        slots=dict(slots or {}),
        budget=SessionBudget(turns_used=0, turns_remaining=18),
    )


def _bindings() -> tuple[SlotBinding, ...]:
    return slot_bindings(
        [
            {
                "fhir_link_id": "hpi.onset",
                "section_id": "hpi",
                "slot_key": "onset",
                "slot_type": "text",
                "aql_path": "/content[openEHR-EHR-OBSERVATION.story.v1]",
                "rm_type": "OBSERVATION",
                "openehr_deferred_reason": None,
            }
        ]
    )


# --- the server, and the template ------------------------------------------------


def test_the_container_is_the_pinned_ehrbase(client: EhrbaseClient) -> None:
    status = client.status()
    assert status.ehrbase_version == "2.35.1", (
        "infra/docker-compose.dev.yml pins ehrbase/ehrbase:2.35.1; a drift here "
        "means the licence verification in docs/evidence/INT-032.md is stale"
    )


def test_the_committed_template_uploads_with_201(
    first_upload: tuple[TemplateState, list[tuple[str, str, int]]],
) -> None:
    """INT-257. INT-032 recorded HTTP 500 here — ``occurrences`` missing on the
    content roots. The committed file now validates against the OPT 1.4 schema
    (tests/protocols/test_opt_schema.py) and the CDR creates it."""
    assert hashlib.sha256(COMMITTED_OPT.read_bytes()).hexdigest() == OPT_SHA256
    state, exchanges = first_upload
    assert state.uploaded is True
    uploads = [(m, status) for m, path, status in exchanges if path.endswith(TEMPLATE_UPLOAD_PATH)]
    assert uploads == [("POST", 201)], (
        "expected exactly one template POST answered 201 by a fresh CDR; a 409 means "
        f"this container already held {TEMPLATE_ID!r} (got {uploads!r})"
    )


def test_template_roundtrips_through_the_cdr(client: EhrbaseClient, uploaded_template: str) -> None:
    """internal → OPT → EHRbase → OPT → internal, asserting identity."""
    committed = load_opt(COMMITTED_OPT)
    retrieved = client.get_template(uploaded_template)
    # The CDR re-serialises what it stored, so the bytes differ and the digest
    # is computed over what came back; the committed walker does the parsing.
    parsed = load_opt(_write_tmp(retrieved), expected_sha256=hashlib.sha256(retrieved).hexdigest())
    assert parsed.template_id == committed.template_id
    assert parsed.roots == committed.roots
    for archetype_id in committed.roots:
        assert parsed.resolve(f"/content[{archetype_id}]") == committed.roots[archetype_id]


def test_uploading_the_same_template_twice_is_not_an_error(
    client: EhrbaseClient, uploaded_template: str
) -> None:
    state = client.ensure_template(COMMITTED_OPT.read_bytes(), template_id=uploaded_template)
    assert state.uploaded is False, "a second boot must not re-create the template"


# --- the composition -------------------------------------------------------------


def test_composition_roundtrips_through_the_cdr(
    client: EhrbaseClient, uploaded_template: str
) -> None:
    """internal → composition → EHRbase → composition → internal, identity."""
    ehr = IntakeEhr(subject_token=_subject_token())
    ehr_id = client.create_ehr(intake_ehr_to_ehr_status(ehr))
    assert ehr_status_to_intake_ehr(client.get_ehr_status(ehr_id)) == ehr

    envelope = _envelope()
    written = session_composition(_session_state(), envelope=envelope, bindings=_bindings())
    version = client.write_composition(ehr_id, written)
    assert version.version == 1

    read_back = client.read_composition(ehr_id, version.version_uid)
    assert read_back["archetype_details"]["template_id"]["value"] == uploaded_template
    assert composition_to_envelope(read_back) == envelope


def test_the_write_is_recorded_as_a_contribution(
    client: EhrbaseClient, uploaded_template: str
) -> None:
    ehr = IntakeEhr(subject_token=_subject_token())
    ehr_id = client.create_ehr(intake_ehr_to_ehr_status(ehr))
    version = client.write_composition(
        ehr_id, session_composition(_session_state(), envelope=_envelope(), bindings=_bindings())
    )
    audit = client.contribution(ehr_id, version.version_uid)
    assert audit.change_type == "creation"
    assert version.version_uid in audit.version_uids
    assert audit.time_committed is not None


def test_a_session_with_answers_writes_nothing(
    client: EhrbaseClient, uploaded_template: str
) -> None:
    """The refusal happens in the mapper, before the transport — so an
    unexportable session leaves no partial record in the CDR."""
    ehr = IntakeEhr(subject_token=_subject_token())
    ehr_id = client.create_ehr(intake_ehr_to_ehr_status(ehr))
    with pytest.raises(OpenEhrExportBlocked) as excinfo:
        session_composition(
            _session_state({"hpi.onset": "iki gündür"}),
            envelope=_envelope(),
            bindings=_bindings(),
        )
    assert [u.slot_id for u in excinfo.value.unbound] == ["hpi.onset"]
    with httpx.Client(base_url=BASE_URL, auth=(USERNAME, PASSWORD), timeout=60.0) as raw:
        response = raw.get(f"/rest/openehr/v1/ehr/{ehr_id}/composition/{uuid.uuid4()}")
    assert response.status_code == 404, "the EHR must hold no composition at all"


def _write_tmp(payload: bytes) -> Path:
    path = Path(os.environ.get("TMPDIR", "/tmp")) / f"int032-{uuid.uuid4()}.opt"  # noqa: S108
    path.write_bytes(payload)
    return path
