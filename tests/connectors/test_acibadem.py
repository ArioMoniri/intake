"""The Acıbadem read connector: the LAN source guard, identity, and login.

Three things are under test and they fail for three different reasons, so
they are kept apart:

* **The guard** (``intake_connectors.sources``) decides whether a request may
  leave at all. The vendor allow-list cannot express this destination — it is
  a private IPv4 literal on a non-standard port over plaintext HTTP, and
  ``EgressPolicy`` refuses each of those three separately — so a second,
  strictly narrower policy exists for it. The tests that matter most here are
  the ones proving the two policies are *disjoint*: this one can only ever
  reach a private literal in its own registry, and it performs no DNS at all.
* **Identity** (``intake_connectors.identity``) is pure. The measured feed
  has null TCs on ten of sixteen rows and one handset shared by two patients,
  so the decision table is the product, and it is tested as a table.
* **The login** (``intake_connectors.acibadem``) composes the two behind the
  consent gate, and never reaches the network before consent answers.

No test here performs a live call. The fixtures under
``tests/fixtures/connectors/acibadem/`` are synthetic rows shaped from the
measured upstream schema, declared in ``infra/ci/no-phi-policy.yaml``.
"""

from __future__ import annotations

import datetime as dt

import httpx
import pytest
from acibadem_harness import (
    ADDRESS,
    CREDENTIAL_REF,
    FAKE_API_KEY,
    PORT,
    TENANT,
    client,
    credentials,
    denied,
    granted,
    json_route,
    load,
    source,
)
from intake_connectors.acibadem import (
    UPCOMING_PATH,
    AcibademLogin,
    AcibademUpstreamError,
    Appointment,
    UpcomingPatient,
    patient_appointments_path,
)
from intake_connectors.credentials import CredentialMissing, EnvCredentialResolver
from intake_connectors.identity import (
    IdentityCandidate,
    IdentityOutcome,
    identifier_digest,
    normalise_tr_msisdn,
    resolve_identity,
    tckn_is_valid,
)
from intake_connectors.sources import (
    LAN_SOURCE_ENV,
    LAN_SOURCE_VALUE,
    ClinicalSource,
    LanSourcePolicy,
    SourceNotRegistered,
    SourceRegistry,
    load_sources,
)
from intake_platform.egress import (
    DataClass,
    EgressContext,
    EgressDenied,
    EgressPolicy,
    EgressPurpose,
    InMemoryTransferLog,
)
from pydantic import ValidationError

TODAY = dt.date(2026, 9, 4)

# The synthetic identifiers the fixtures carry. Repeated here rather than read
# out of the fixture so a test that asserts "this value never appears" has a
# literal to look for.
SHARED_PHONE = "905321110001"
SHARED_PHONE_LOCAL = "0532 111 00 01"
SOLO_PHONE = "905321110003"
MEHMET_TCKN = "10000000146"
AYSE_TCKN = "12345678950"
UNRELATED_TCKN = "27182818254"


# ---------------------------------------------------------------------------
# Phone normalisation — both sides, or nothing ever matches
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # The three spellings that actually collide in this system: the feed
        # writes 905…, the app's own phone screen produces 05…, and E.164 is
        # what the OTP tier stores.
        ("905321110001", "+905321110001"),
        ("05321110001", "+905321110001"),
        ("+905321110001", "+905321110001"),
        ("5321110001", "+905321110001"),
        ("0532 111 00 01", "+905321110001"),
        ("0532-111-00-01", "+905321110001"),
        ("(0532) 111 00 01", "+905321110001"),
        # Not Turkish mobiles.
        ("902121110001", None),
        ("021211100 01", None),
        ("", None),
        ("53211100010", None),
        ("+445321110001", None),
        ("0532111000", None),
        (None, None),
    ],
)
def test_a_turkish_mobile_normalises_to_one_canonical_form(
    raw: str | None, expected: str | None
) -> None:
    assert normalise_tr_msisdn(raw) == expected


def test_the_feeds_spelling_and_the_apps_spelling_normalise_to_the_same_value() -> None:
    """The single measured fact that would silently break every login.

    The feed stores twelve characters beginning ``905``; the app's phone
    screen produces ``05…``. Comparing either raw form to the other matches
    nothing, and the failure looks exactly like "the patient is not in the
    feed".
    """
    assert normalise_tr_msisdn(SHARED_PHONE) == normalise_tr_msisdn(SHARED_PHONE_LOCAL)


def test_the_connector_normaliser_agrees_with_the_otp_tiers_normaliser() -> None:
    """Two normalisers, one canonical form.

    The OTP tier already owns ``normalise_tr_phone`` and its output is what a
    verified session carries. A second implementation here is only safe while
    the two agree on every spelling that reaches either of them, so the
    agreement is pinned rather than assumed.
    """
    from intake_api.otp import normalise_tr_phone

    for raw in ("905321110001", "05321110001", "+905321110001", "5321110001", "0532 111 00 01"):
        assert normalise_tr_msisdn(raw) == normalise_tr_phone(raw)
    for rejected in ("902121110001", "", "0532111000"):
        assert normalise_tr_msisdn(rejected) == normalise_tr_phone(rejected) is None


# ---------------------------------------------------------------------------
# TC Kimlik — a checksum, never a secret
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "valid"),
    [
        (MEHMET_TCKN, True),
        (AYSE_TCKN, True),
        ("22222222220", True),
        ("31415926562", True),
        # d11 flipped.
        ("10000000147", False),
        # d10 flipped.
        ("10000000156", False),
        # Leading zero is never a TC Kimlik.
        ("01000000146", False),
        ("1000000014", False),
        ("100000001466", False),
        ("1000000014a", False),
        ("", False),
        (None, False),
    ],
)
def test_the_tc_checksum_is_computed_not_assumed(value: str | None, valid: bool) -> None:
    assert tckn_is_valid(value) is valid


def test_a_digest_is_stable_truncated_and_not_the_value() -> None:
    digest = identifier_digest(MEHMET_TCKN)
    assert digest == identifier_digest(MEHMET_TCKN)
    assert len(digest) == 16
    assert MEHMET_TCKN not in digest


def test_the_connector_checksum_is_the_gates_checksum() -> None:
    """One implementation of the TC Kimlik algorithm, pinned to the other.

    ``scripts/ci/tckn_check.py`` has carried this arithmetic since INT-019 and
    is not importable as a package, so the runtime copy here is a second
    implementation of a published algorithm. A second implementation is only
    safe while the two agree, so the agreement is a test rather than a
    comment.
    """
    import importlib.util
    from pathlib import Path

    helper = Path("scripts/ci/tckn_check.py").resolve()
    spec = importlib.util.spec_from_file_location("tckn_check", helper)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    table = (
        MEHMET_TCKN,
        AYSE_TCKN,
        UNRELATED_TCKN,
        "22222222220",
        "31415926562",
        "90000000100",
        "10000000147",
        "10000000156",
        "12345678951",
        "99999999999",
    )
    for value in table:
        assert tckn_is_valid(value) is module.is_valid_tckn(value), value


def test_the_connector_digest_is_the_repositorys_own_digest() -> None:
    """One definition of "safe to print". A second would drift."""
    from intake_platform.ci.phi import identifier_digest as ci_digest

    assert identifier_digest(MEHMET_TCKN) == ci_digest(MEHMET_TCKN)


# ---------------------------------------------------------------------------
# Identity resolution — the decision table, including the refusals
# ---------------------------------------------------------------------------


def candidates() -> tuple[IdentityCandidate, ...]:
    return tuple(
        UpcomingPatient.model_validate(row).as_candidate() for row in load("upcoming.json")["data"]
    )


def test_one_phone_match_is_the_patient() -> None:
    resolution = resolve_identity(candidates(), phone="+905321110003")
    assert resolution.outcome is IdentityOutcome.MATCHED
    assert resolution.patient_number == "40000003"
    assert resolution.candidate_count == 1


def test_a_local_spelling_matches_a_row_stored_in_the_feeds_spelling() -> None:
    """The near-miss control the measured data demands: ``05…`` against ``905…``."""
    normalised = normalise_tr_msisdn(SHARED_PHONE_LOCAL)
    assert normalised is not None
    resolution = resolve_identity(candidates(), phone=normalised, tckn=MEHMET_TCKN)
    assert resolution.outcome is IdentityOutcome.MATCHED
    assert resolution.patient_number == "40000001"


def test_a_shared_handset_without_a_tc_asks_for_one_rather_than_guessing() -> None:
    resolution = resolve_identity(candidates(), phone="+905321110001")
    assert resolution.outcome is IdentityOutcome.NEEDS_TCKN
    assert resolution.patient_number is None
    assert resolution.candidate_count == 2
    assert resolution.reason == "tckn_required"


def test_a_shared_handset_resolves_on_the_tc_that_belongs_to_one_of_them() -> None:
    for tckn, expected in ((MEHMET_TCKN, "40000001"), (AYSE_TCKN, "40000002")):
        resolution = resolve_identity(candidates(), phone="+905321110001", tckn=tckn)
        assert resolution.outcome is IdentityOutcome.MATCHED
        assert resolution.patient_number == expected
        assert resolution.reason == "tckn_disambiguated"


def test_a_wrong_tc_on_a_shared_handset_is_refused_and_matches_nobody() -> None:
    """The control that keeps one patient off another patient's visit.

    A TC that belongs to neither candidate must not fall back to "well, the
    OTP passed, show them the first one". The refusal is terminal, not a
    prompt: re-asking would turn the field into an oracle.
    """
    resolution = resolve_identity(candidates(), phone="+905321110001", tckn=UNRELATED_TCKN)
    assert resolution.outcome is IdentityOutcome.REFUSED_AMBIGUOUS
    assert resolution.patient_number is None
    assert resolution.reason == "tckn_no_match"


def test_a_shared_handset_where_neither_row_carries_a_tc_refuses_without_asking() -> None:
    """Ten of sixteen measured rows have a null TC. When both candidates are
    among them there is nothing to disambiguate with, so asking the patient
    for a TC would be a dead end dressed as a prompt."""
    resolution = resolve_identity(candidates(), phone="+905321110007")
    assert resolution.outcome is IdentityOutcome.REFUSED_AMBIGUOUS
    assert resolution.reason == "no_tckn_available"


def test_a_null_tc_row_is_never_matched_by_a_supplied_tc() -> None:
    rows = (
        IdentityCandidate(patient_number="A1", msisdn="+905321110099", tckn=None),
        IdentityCandidate(patient_number="A2", msisdn="+905321110099", tckn=None),
    )
    assert resolve_identity(rows, phone="+905321110099", tckn=MEHMET_TCKN).outcome is (
        IdentityOutcome.REFUSED_AMBIGUOUS
    )


def test_a_malformed_tc_is_not_used_as_a_disambiguator() -> None:
    resolution = resolve_identity(candidates(), phone="+905321110001", tckn="10000000147")
    assert resolution.outcome is IdentityOutcome.NEEDS_TCKN
    assert resolution.reason == "tckn_invalid"


def test_an_unknown_phone_matches_nothing() -> None:
    resolution = resolve_identity(candidates(), phone="+905329999999")
    assert resolution.outcome is IdentityOutcome.NO_MATCH
    assert resolution.candidate_count == 0


def test_a_row_without_a_phone_can_never_be_reached_by_phone() -> None:
    """One measured row of sixteen has a null ``cell_phone``. It must not be
    matched by a caller who supplies no phone either."""
    rows = candidates()
    assert any(row.msisdn is None for row in rows)
    with pytest.raises(ValueError, match="normalised"):
        resolve_identity(rows, phone="not-a-phone")


def test_a_resolution_carries_ids_and_counts_and_no_identifier() -> None:
    resolution = resolve_identity(candidates(), phone="+905321110001", tckn=UNRELATED_TCKN)
    rendered = repr(resolution)
    for secret in (SHARED_PHONE, UNRELATED_TCKN, MEHMET_TCKN, "YILMAZ", "MEHMET"):
        assert secret not in rendered


def test_a_candidate_never_prints_its_own_identifiers() -> None:
    candidate = IdentityCandidate(
        patient_number="40000001", msisdn="+905321110001", tckn=MEHMET_TCKN
    )
    for rendered in (repr(candidate), str(candidate)):
        assert MEHMET_TCKN not in rendered
        assert "905321110001" not in rendered
        assert "40000001" in rendered


# ---------------------------------------------------------------------------
# The source row: what may be registered, and what may not
# ---------------------------------------------------------------------------


def test_a_source_row_accepts_a_private_literal_because_that_is_the_only_thing_it_accepts() -> None:
    row = source()
    assert row.address == ADDRESS
    assert row.port == PORT


@pytest.mark.parametrize(
    "address",
    [
        # A public address: this class exists for on-premises hospital LANs,
        # and a public literal is exactly what the vendor allow-list refuses.
        "203.0.113.10",
        "8.8.8.8",
        # The SSRF targets the original ban was written against.
        "169.254.169.254",
        "127.0.0.1",
        "0.0.0.0",  # noqa: S104 - the point of the row is that it is refused
        # A hostname is not an address: a name would reintroduce the DNS this
        # policy deliberately does not perform.
        "hbys.example.test",
        "localhost",
        # Not addresses at all.
        "http://10.150.0.42",
        "10.150.0.42:8091",
        "10.150.0.42/api",
        "::1",
        "fd00::1",
        "",
    ],
)
def test_a_source_row_refuses_every_address_that_is_not_a_private_ipv4_literal(
    address: str,
) -> None:
    with pytest.raises(ValidationError):
        source(address=address)


def test_plaintext_requires_its_own_recorded_approval() -> None:
    """Invariant 14's transport half. A clinical feed carrying TC numbers over
    unencrypted HTTP is a decision a human takes and records, not a default
    the schema hands out."""
    with pytest.raises(ValidationError, match="plaintext_approval"):
        source(plaintext_approval=None)


def test_https_does_not_need_a_plaintext_approval() -> None:
    row = source(protocol="https", port=443, plaintext_approval=None)
    assert row.protocol == "https"


def test_a_source_row_names_a_consent_scope_the_registry_actually_defines() -> None:
    """Invariant 4 at load time. A row naming a purpose no docs/legal text
    binds cannot be registered, so the read it authorises cannot happen."""
    with pytest.raises(ValidationError, match="consent purpose"):
        source(consent_scope="hospital:appointments")


def test_a_credential_reference_stays_under_the_connector_root() -> None:
    with pytest.raises(ValidationError):
        source(credential_ref="secret/of/another/service")


def test_a_base_path_cannot_name_a_host_or_traverse() -> None:
    for bad in ("//evil.example", "/api?x=1", "/api/../..", "/api#frag"):
        with pytest.raises(ValidationError):
            source(base_path=bad)


def test_the_shipped_source_registry_holds_no_rows() -> None:
    """The fail-closed state, not a gap — the same one
    ``infra/connectors/destinations.yaml`` ships in.

    Registering the Acıbadem row needs three values no agent may mint: a
    consent purpose id (blocked by HB-L27), a tier-3 approval for the read,
    and a second approval for carrying clinical identifiers in plaintext.
    """
    from pathlib import Path

    registry = load_sources(Path("infra/connectors/sources.yaml"))
    assert registry.rows == ()
    with pytest.raises(SourceNotRegistered):
        registry.resolve(tenant_id=TENANT, source_id="acibadem-appointments-lan")


def test_a_row_is_addressed_by_tenant_and_source_together() -> None:
    registry = SourceRegistry([source()])
    assert (
        registry.resolve(tenant_id=TENANT, source_id="acibadem-appointments-lan").address == ADDRESS
    )
    with pytest.raises(SourceNotRegistered):
        registry.resolve(tenant_id="tenant-other", source_id="acibadem-appointments-lan")


# ---------------------------------------------------------------------------
# The LAN guard: default deny twice, disjoint from the vendor allow-list
# ---------------------------------------------------------------------------


READ = EgressContext(purpose=EgressPurpose.CLINICAL_RECORD_READ, data_class=DataClass.PHI)


def test_the_registered_address_and_port_are_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(LAN_SOURCE_ENV, LAN_SOURCE_VALUE)
    decision = LanSourcePolicy(source()).check(ADDRESS, PORT, READ)
    assert decision.allowed is True
    assert decision.purpose is EgressPurpose.CLINICAL_RECORD_READ


def test_a_second_address_on_the_same_lan_is_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(LAN_SOURCE_ENV, LAN_SOURCE_VALUE)
    assert LanSourcePolicy(source()).check("10.150.0.43", PORT, READ).allowed is False


def test_a_second_port_on_the_registered_address_is_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(LAN_SOURCE_ENV, LAN_SOURCE_VALUE)
    assert LanSourcePolicy(source()).check(ADDRESS, 8092, READ).allowed is False


def test_a_hostname_is_denied_so_this_policy_can_never_reach_a_public_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The containment property. ``EgressPolicy`` refuses every literal;
    ``LanSourcePolicy`` refuses every name. The two reach disjoint sets of
    destinations, so neither is a way around the other."""
    monkeypatch.setenv(LAN_SOURCE_ENV, LAN_SOURCE_VALUE)
    policy = LanSourcePolicy(source())
    for host in ("hbys.example.test", "10.150.0.42.nip.io", "pypi.org"):
        assert policy.check(host, PORT, READ).allowed is False


def test_the_vendor_policy_still_refuses_the_literal_this_one_serves() -> None:
    """Nothing here widened the vendor allow-list."""
    vendor = EgressPolicy([], "phi_path")
    decision = vendor.check(ADDRESS, PORT, READ)
    assert decision.allowed is False
    assert "literal IP" in decision.reason


def test_the_purpose_is_a_permission_here_too(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(LAN_SOURCE_ENV, LAN_SOURCE_VALUE)
    push = EgressContext(purpose=EgressPurpose.CLINICAL_RECORD_PUSH, data_class=DataClass.PHI)
    decision = LanSourcePolicy(source()).check(ADDRESS, PORT, push)
    assert decision.allowed is False
    assert "purpose" in decision.reason


def test_the_runtime_gate_denies_even_a_registered_row(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default deny twice: config alone is not enough (ADR-025's shape)."""
    monkeypatch.delenv(LAN_SOURCE_ENV, raising=False)
    decision = LanSourcePolicy(source()).check(ADDRESS, PORT, READ)
    assert decision.allowed is False
    assert LAN_SOURCE_ENV in decision.reason


def test_a_denied_request_never_reaches_the_inner_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(LAN_SOURCE_ENV, raising=False)
    reached: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:  # pragma: no cover - must not run
        reached.append(request.url.path)
        return httpx.Response(200, json={})

    log = InMemoryTransferLog()
    api = client(httpx.MockTransport(handle), transfer_log=log)
    with pytest.raises(EgressDenied):
        api.upcoming()
    assert reached == []
    assert [entry.decision for entry in log.entries] == ["deny"]
    assert log.entries[0].bytes_out == 0


def test_every_decision_reaches_the_transfer_register(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(LAN_SOURCE_ENV, LAN_SOURCE_VALUE)
    log = InMemoryTransferLog()
    api = client(json_route({UPCOMING_PATH: (200, load("upcoming.json"))}), transfer_log=log)
    api.upcoming()
    (entry,) = log.entries
    assert entry.decision == "allow"
    assert entry.host == ADDRESS
    assert entry.port == PORT
    assert entry.purpose is EgressPurpose.CLINICAL_RECORD_READ
    assert entry.data_class is DataClass.PHI


# ---------------------------------------------------------------------------
# The credential: environment only, no in-code default, never rendered
# ---------------------------------------------------------------------------


def test_the_api_key_comes_from_the_environment_with_no_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ACIBADEM_API_KEY", raising=False)
    resolver = EnvCredentialResolver({CREDENTIAL_REF: {"api_key": "ACIBADEM_API_KEY"}})
    with pytest.raises(CredentialMissing):
        resolver.read(CREDENTIAL_REF)


def test_an_empty_environment_value_is_a_missing_credential_not_an_empty_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ACIBADEM_API_KEY", "")
    resolver = EnvCredentialResolver({CREDENTIAL_REF: {"api_key": "ACIBADEM_API_KEY"}})
    with pytest.raises(CredentialMissing):
        resolver.read(CREDENTIAL_REF)


def test_the_environment_resolver_reads_only_variables_it_was_told_about(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ACIBADEM_API_KEY", FAKE_API_KEY)
    resolver = EnvCredentialResolver({CREDENTIAL_REF: {"api_key": "ACIBADEM_API_KEY"}})
    assert resolver.read(CREDENTIAL_REF) == {"api_key": FAKE_API_KEY}
    with pytest.raises(CredentialMissing):
        resolver.read("connectors/somebody-else/api-key")


def test_a_missing_credential_names_no_value_and_no_store_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(LAN_SOURCE_ENV, LAN_SOURCE_VALUE)
    api = client(json_route({}), resolver=credentials({}))
    with pytest.raises(CredentialMissing) as caught:
        api.upcoming()
    assert CREDENTIAL_REF not in str(caught.value)
    assert FAKE_API_KEY not in str(caught.value)


def test_the_key_travels_in_the_x_api_key_header_and_nowhere_else(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(LAN_SOURCE_ENV, LAN_SOURCE_VALUE)
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=load("upcoming.json"))

    client(httpx.MockTransport(handle)).upcoming()
    (request,) = seen
    assert request.headers["x-api-key"] == FAKE_API_KEY
    assert "authorization" not in request.headers
    assert FAKE_API_KEY not in str(request.url)
    assert request.url.query == b""


# ---------------------------------------------------------------------------
# Parsing the measured shape
# ---------------------------------------------------------------------------


def test_the_upcoming_feed_parses_into_typed_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(LAN_SOURCE_ENV, LAN_SOURCE_VALUE)
    rows = client(json_route({UPCOMING_PATH: (200, load("upcoming.json"))})).upcoming()
    assert len(rows) == 8
    assert sum(1 for row in rows if row.tckimlik_no is None) == 4
    assert sum(1 for row in rows if row.cell_phone is None) == 1


def test_an_appointment_row_keeps_the_upstream_time_string_and_derives_no_other(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``start_time`` is a five-minute slot index, and the measured feed
    carries at least one row where it is a sentinel that decodes to 25:00.
    ``randevu_saati`` is the field of record; nothing is computed from the
    integer."""
    monkeypatch.setenv(LAN_SOURCE_ENV, LAN_SOURCE_VALUE)
    api = client(
        json_route({patient_appointments_path("40000003"): (200, load("patient_40000003.json"))})
    )
    rows = api.appointments_for("40000003")
    assert [row.appointment_date for row in rows] == [
        dt.date(2026, 9, 5),
        dt.date(2026, 9, 5),
        dt.date(2021, 10, 11),
    ]
    assert [row.appointment_time.isoformat("minutes") for row in rows] == [
        "13:00",
        "13:05",
        "08:15",
    ]
    assert rows[1].start_time == 300


def test_a_row_the_upstream_returned_for_somebody_else_is_dropped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Never trust the receiver's own filtering. The upstream answers the
    per-patient path with rows it selected; the client re-checks that every
    row carries the number it asked for."""
    monkeypatch.setenv(LAN_SOURCE_ENV, LAN_SOURCE_VALUE)
    api = client(
        json_route(
            {
                patient_appointments_path("40000006"): (
                    200,
                    load("patient_40000006_foreign_row.json"),
                )
            }
        )
    )
    rows = api.appointments_for("40000006")
    assert [row.patient_number for row in rows] == ["40000006"]


@pytest.mark.parametrize(
    "patient_number",
    [
        "../../health",
        "40000003/../40000004",
        "40000003?x=1",
        "4000 0003",
        "",
        "a" * 64,
        "40000003#f",
    ],
)
def test_a_patient_number_that_could_reshape_the_path_is_refused(patient_number: str) -> None:
    with pytest.raises(ValueError):
        patient_appointments_path(patient_number)


def test_a_non_numeric_patient_number_from_the_feed_still_builds_a_safe_path() -> None:
    """One measured row of sixteen carries a patient number that is letters
    and a full stop, and the upstream answers 422 for it. It must still be
    expressible — refusing it here would hide the upstream's own answer."""
    assert patient_appointments_path("ABCDEFG.") == "/api/v1/patients/ABCDEFG./appointments"


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (401, "unauthorized"),
        (404, "not_found"),
        (422, "unprocessable"),
        (500, "upstream_error"),
        (503, "upstream_error"),
    ],
)
def test_an_upstream_failure_is_a_code_and_never_a_body(
    monkeypatch: pytest.MonkeyPatch, status: int, code: str
) -> None:
    monkeypatch.setenv(LAN_SOURCE_ENV, LAN_SOURCE_VALUE)
    body = {"detail": f"patient MEHMET YILMAZ {MEHMET_TCKN} not found"}
    api = client(json_route({UPCOMING_PATH: (status, body)}))
    with pytest.raises(AcibademUpstreamError) as caught:
        api.upcoming()
    assert caught.value.code == code
    rendered = str(caught.value)
    assert MEHMET_TCKN not in rendered
    assert "MEHMET" not in rendered
    assert "not found" not in rendered


def test_a_body_that_is_not_the_documented_shape_is_a_code_not_a_traceback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(LAN_SOURCE_ENV, LAN_SOURCE_VALUE)
    for body in (b"<html>login</html>", b'{"data": "not a list"}', b'{"count": 1}'):
        api = client(json_route({UPCOMING_PATH: (200, body)}))
        with pytest.raises(AcibademUpstreamError) as caught:
            api.upcoming()
        assert caught.value.code == "malformed"


def test_a_parsed_row_never_prints_its_own_identifiers() -> None:
    row = Appointment.model_validate(load("patient_40000003.json")["data"][0])
    for rendered in (repr(row), str(row)):
        assert SOLO_PHONE not in rendered
        assert "FATMA" not in rendered
        assert "KAYA" not in rendered
        assert "40000003" in rendered


def test_an_upcoming_row_never_prints_its_own_identifiers() -> None:
    row = UpcomingPatient.model_validate(load("upcoming.json")["data"][0])
    for rendered in (repr(row), str(row)):
        assert MEHMET_TCKN not in rendered
        assert SHARED_PHONE not in rendered
        assert "MEHMET" not in rendered


# ---------------------------------------------------------------------------
# The login: consent first, then the network
# ---------------------------------------------------------------------------


def login(handler: httpx.MockTransport, consent=granted) -> AcibademLogin:
    return AcibademLogin(client=client(handler), consent=consent)


def test_a_verified_phone_returns_that_patients_upcoming_visits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(LAN_SOURCE_ENV, LAN_SOURCE_VALUE)
    service = login(
        json_route(
            {
                UPCOMING_PATH: (200, load("upcoming.json")),
                patient_appointments_path("40000003"): (200, load("patient_40000003.json")),
            }
        )
    )
    result = service.sign_in(
        tenant_id=TENANT, patient_ref="patient-1", phone="0532 111 00 03", today=TODAY
    )
    assert result.outcome is IdentityOutcome.MATCHED
    assert result.patient_number == "40000003"
    # The past visit is dropped: the per-patient endpoint returns the whole
    # history, not the upcoming window the list endpoint advertises.
    assert [row.appointment_date for row in result.appointments] == [
        dt.date(2026, 9, 5),
        dt.date(2026, 9, 5),
    ]
    assert [row.appointment_time.isoformat("minutes") for row in result.appointments] == [
        "13:00",
        "13:05",
    ]


def test_a_shared_handset_login_refuses_and_returns_no_appointments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Showing one patient another's visit is worse than a failed login."""
    monkeypatch.setenv(LAN_SOURCE_ENV, LAN_SOURCE_VALUE)
    service = login(json_route({UPCOMING_PATH: (200, load("upcoming.json"))}))
    result = service.sign_in(
        tenant_id=TENANT,
        patient_ref="patient-1",
        phone=SHARED_PHONE,
        tckn=UNRELATED_TCKN,
        today=TODAY,
    )
    assert result.outcome is IdentityOutcome.REFUSED_AMBIGUOUS
    assert result.patient_number is None
    assert result.appointments == ()


def test_a_shared_handset_login_without_a_tc_asks_for_one(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(LAN_SOURCE_ENV, LAN_SOURCE_VALUE)
    service = login(json_route({UPCOMING_PATH: (200, load("upcoming.json"))}))
    result = service.sign_in(
        tenant_id=TENANT, patient_ref="patient-1", phone=SHARED_PHONE, today=TODAY
    )
    assert result.outcome is IdentityOutcome.NEEDS_TCKN
    assert result.appointments == ()


def test_consent_is_checked_before_anything_leaves_the_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invariant 4. A refused consent must not become a request that was made
    and then discarded — the read is what needs authorising, not the answer."""
    monkeypatch.setenv(LAN_SOURCE_ENV, LAN_SOURCE_VALUE)
    reached: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:  # pragma: no cover - must not run
        reached.append(request.url.path)
        return httpx.Response(200, json=load("upcoming.json"))

    service = login(httpx.MockTransport(handle), consent=denied)
    result = service.sign_in(
        tenant_id=TENANT, patient_ref="patient-1", phone=SOLO_PHONE, today=TODAY
    )
    assert result.outcome is IdentityOutcome.NO_MATCH
    assert result.reason == "consent_absent"
    assert reached == []


def test_the_consent_gate_is_asked_for_the_rows_declared_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(LAN_SOURCE_ENV, LAN_SOURCE_VALUE)
    asked: list[tuple[str, str, str]] = []

    def gate(*, tenant_id: str, patient_ref: str, scope: str):
        asked.append((tenant_id, patient_ref, scope))
        return granted()

    service = login(json_route({UPCOMING_PATH: (200, load("upcoming.json"))}), consent=gate)
    service.sign_in(tenant_id=TENANT, patient_ref="patient-1", phone="+905329999999", today=TODAY)
    assert asked == [(TENANT, "patient-1", "core")]


def test_a_failed_login_echoes_neither_the_phone_nor_the_tc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(LAN_SOURCE_ENV, LAN_SOURCE_VALUE)
    service = login(json_route({UPCOMING_PATH: (200, load("upcoming.json"))}))
    result = service.sign_in(
        tenant_id=TENANT,
        patient_ref="patient-1",
        phone=SHARED_PHONE,
        tckn=UNRELATED_TCKN,
        today=TODAY,
    )
    rendered = repr(result)
    for secret in (SHARED_PHONE, UNRELATED_TCKN, "+905321110001"):
        assert secret not in rendered


def test_a_phone_that_is_not_a_turkish_mobile_never_reaches_the_upstream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(LAN_SOURCE_ENV, LAN_SOURCE_VALUE)
    reached: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:  # pragma: no cover - must not run
        reached.append(request.url.path)
        return httpx.Response(200, json=load("upcoming.json"))

    result = login(httpx.MockTransport(handle)).sign_in(
        tenant_id=TENANT, patient_ref="patient-1", phone="not-a-phone", today=TODAY
    )
    assert result.outcome is IdentityOutcome.NO_MATCH
    assert result.reason == "phone_not_normalisable"
    assert reached == []


def test_the_client_aims_at_the_registered_address_and_never_at_a_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(LAN_SOURCE_ENV, LAN_SOURCE_VALUE)
    seen: list[httpx.URL] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        return httpx.Response(200, json=load("upcoming.json"))

    client(httpx.MockTransport(handle)).upcoming()
    (url,) = seen
    assert url.host == ADDRESS
    assert url.port == PORT
    assert url.scheme == "http"
    assert url.path == UPCOMING_PATH


def test_a_source_declares_the_read_purpose_and_the_phi_data_class() -> None:
    context = source().egress_context()
    assert context.purpose is EgressPurpose.CLINICAL_RECORD_READ
    assert context.data_class is DataClass.PHI


def test_the_read_purpose_is_not_the_push_purpose() -> None:
    """A purpose is a permission (ADR-025). A read endpoint that inherited the
    push purpose would be a destination approved to *receive* patient records."""
    assert EgressPurpose.CLINICAL_RECORD_READ is not EgressPurpose.CLINICAL_RECORD_PUSH


def test_a_clinical_source_is_frozen() -> None:
    row = source()
    with pytest.raises(ValidationError):
        row.address = "10.0.0.1"  # type: ignore[misc]


def test_a_clinical_source_row_refuses_an_unknown_field() -> None:
    with pytest.raises(ValidationError):
        ClinicalSource.model_validate({**source().model_dump(), "follow_redirects": True})
