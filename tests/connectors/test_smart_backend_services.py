"""INT-161 — SMART backend services: a second auth mode, and a second host.

INT-160 gave ``auth_mode`` exactly one member and said so in the schema: SMART
"arrives with the FHIR adapter (INT-161) as an added member, never as a
relaxation of this one". This file is that member and the case that it relaxes
nothing.

**Why a second member was unavoidable.** ``mtls`` authenticates the *channel*
with material OpenBao already holds, so a push is one request. SMART
authenticates the *client* with a signed assertion exchanged for a short-lived
access token, so a push is two requests to two hosts — and the second host is
not a detail. ADR-025's fifth bypass is "the right host addressed for the
wrong reason"; INT-160 met it as a host contracted for a *different tenant*
and answered with the tenant dimension. A token endpoint is the same bypass in
a third form: a host that is contracted, approved and on this very tenant's
row, for a purpose that is **not** receiving clinical records. So it gets its
own allow-list entry, its own purpose (``CONNECTOR_AUTHORIZATION``) and
``phi_allowed: false`` — and the two entries refuse each other's traffic.

**What changes for OpenBao.** ``mtls`` reads two documents: a bearer under
``credential_ref`` and certificate material under ``client_cert_ref``. SMART
reads one: ``credential_ref`` holds ``{client_id, private_key}`` and an
optional ``key_id``, both still under the ``connectors/`` subtree the
connector policy is the only reader of. ``client_cert_ref`` becomes optional
*for SMART only* — a hospital that authenticates with an assertion has no
client certificate to issue, and requiring one would make the row unfillable —
and stays required for ``mtls``, which is where the test below points.

**No token cache.** One assertion, one token, one push. A cached token is a
credential that outlives the consent check that authorised it, and INT-160
already refused to cache the consent verdict for exactly that reason.
"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs

import httpx
import pytest
from connector_harness import (
    FAKE_ACCESS_TOKEN,
    FHIR_HOST,
    PUBLIC_ANSWER,
    PUBLIC_ANSWER_TOKEN,
    SMART_SCOPE,
    TOKEN_HOST,
    granted_until,
    refused,
    smart_credentials,
    smart_destination,
    smart_key_pem,
    smart_push,
    smart_sender,
)
from cryptography.hazmat.primitives.asymmetric import ec
from intake_connectors import (
    ClinicalPayload,
    ConnectorDestination,
    ConsentDenied,
    ReceiptState,
)
from intake_platform.egress import DataClass, EgressPurpose

FHIR_JSON = "application/fhir+json"
ASSERTION_TYPE = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"


def payload() -> ClinicalPayload:
    return ClinicalPayload(body=b'{"resourceType":"Bundle","type":"document"}', media_type=FHIR_JSON)


def form_of(request: httpx.Request) -> dict[str, str]:
    return {key: values[0] for key, values in parse_qs(request.content.decode()).items()}


def jwt_parts(token: str) -> tuple[dict[str, object], dict[str, object], bytes]:
    header_b64, claims_b64, signature_b64 = token.split(".")

    def decode(segment: str) -> bytes:
        return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))

    return (
        json.loads(decode(header_b64)),
        json.loads(decode(claims_b64)),
        decode(signature_b64),
    )


def assertion_of(request: httpx.Request) -> tuple[dict[str, object], dict[str, object], bytes]:
    return jwt_parts(form_of(request)["client_assertion"])


# --- 1. the schema: a second member that relaxes nothing ----------------------------


def test_smart_is_a_second_auth_mode_and_the_first_is_unchanged() -> None:
    assert smart_destination().auth_mode == "smart_backend_services"
    with pytest.raises(ValueError, match="client_cert_ref"):
        ConnectorDestination.model_validate(
            {
                **smart_destination().model_dump(),
                "auth_mode": "mtls",
                "client_cert_ref": None,
            }
        )


def test_a_smart_row_must_declare_its_token_endpoint_and_its_scope() -> None:
    for missing in ("token_host", "smart_scope"):
        with pytest.raises(ValueError, match=missing):
            smart_destination(**{missing: None})


def test_an_mtls_row_may_not_declare_a_token_endpoint() -> None:
    """A field that only one mode reads is a field the other mode must not
    carry: a row that names a token host and never uses it is a destination
    nobody reviews."""
    with pytest.raises(ValueError, match="token"):
        ConnectorDestination.model_validate(
            {
                **smart_destination().model_dump(),
                "auth_mode": "mtls",
                "client_cert_ref": "connectors/t/e/mtls",
            }
        )


@pytest.mark.parametrize(
    "token_host",
    ["169.254.169.254", "openbao", "https://auth.example.test", "auth.example.test:8443", "*.a.test"],
)
def test_the_token_host_obeys_the_same_hostname_grammar(token_host: str) -> None:
    with pytest.raises(ValueError):
        smart_destination(token_host=token_host)


@pytest.mark.parametrize("token_path", ["/oauth2/../../admin", "/oauth2/token?x=1", "//evil.test"])
def test_the_token_path_cannot_smuggle_a_second_destination(token_path: str) -> None:
    with pytest.raises(ValueError):
        smart_destination(token_path=token_path)


def test_the_credential_reference_still_lives_under_the_connectors_subtree() -> None:
    with pytest.raises(ValueError, match="connectors/"):
        smart_destination(credential_ref="secret/other/team")


# --- 2. the second host, and ADR-025's fifth bypass in its third form ---------------


def test_the_token_exchange_gets_its_own_entry_that_may_not_carry_phi() -> None:
    entry = smart_destination().authorization_egress_entry()
    assert entry.host == TOKEN_HOST
    assert entry.purpose_id is EgressPurpose.CONNECTOR_AUTHORIZATION
    assert entry.phi_allowed is False, "no clinical byte is ever sent to a token endpoint"
    assert entry.phi_exception_approval is None


def test_the_push_entry_and_the_authorization_entry_are_different_permissions() -> None:
    row = smart_destination()
    push_entry, auth_entry = row.egress_entry(), row.authorization_egress_entry()
    assert push_entry.purpose_id is not auth_entry.purpose_id
    assert push_entry.phi_allowed and not auth_entry.phi_allowed


def test_one_host_serving_both_roles_still_needs_both_purposes() -> None:
    """The common real deployment: the authorization server and the FHIR
    server are the same name. Two entries, two purposes, still — because a
    purpose is a permission and sharing a hostname is not sharing one."""
    row = smart_destination(token_host=FHIR_HOST)
    assert row.egress_entry().host == row.authorization_egress_entry().host
    assert row.egress_entry().purpose_id is not row.authorization_egress_entry().purpose_id


def test_a_token_host_that_resolves_into_a_denied_range_is_refused() -> None:
    sender, push_transport, token_transport = smart_sender(
        dns={FHIR_HOST: [PUBLIC_ANSWER], TOKEN_HOST: ["169.254.169.254"]}
    )
    receipt = sender.send(smart_push(), payload())
    assert receipt.state is ReceiptState.FAILED
    assert receipt.outcome_code == "smart_egress_denied"
    assert token_transport.requests == [] and push_transport.requests == []


def test_the_token_endpoint_is_registry_data_and_is_never_discovered() -> None:
    """No ``/.well-known/smart-configuration``.

    Discovery lets the *receiver* nominate where our client credential is
    sent, which is a redirect to an unchecked host wearing a standard's name.
    The audience of the assertion is built from the registry row, and the
    only request that leaves is the token request itself.
    """
    sender, _, token_transport = smart_sender()
    sender.send(smart_push(), payload())
    (request,) = token_transport.requests
    assert request.url.path == "/oauth2/token"
    assert ".well-known" not in str(request.url)


def test_the_authorization_request_is_declared_as_carrying_no_personal_data() -> None:
    from intake_platform.egress import InMemoryTransferLog

    log = InMemoryTransferLog()
    sender, _, _ = smart_sender(transfer_log=log)
    sender.send(smart_push(), payload())
    auth_record, push_record = log.entries
    assert auth_record.host == TOKEN_HOST
    assert auth_record.purpose is EgressPurpose.CONNECTOR_AUTHORIZATION
    assert auth_record.data_class is DataClass.NON_PERSONAL
    assert push_record.host == FHIR_HOST
    assert push_record.data_class is DataClass.PHI


def test_no_clinical_byte_reaches_the_token_endpoint() -> None:
    body = b'{"resourceType":"Bundle","type":"document","id":"note-secret"}'
    sender, _, token_transport = smart_sender()
    sender.send(smart_push(), ClinicalPayload(body=body, media_type=FHIR_JSON))
    (request,) = token_transport.requests
    assert b"note-secret" not in request.content
    assert request.headers["content-type"] == "application/x-www-form-urlencoded"


def test_the_two_hosts_are_pinned_to_their_own_answers() -> None:
    sender, push_transport, token_transport = smart_sender()
    sender.send(smart_push(), payload())
    assert token_transport.requests[0].url.host == PUBLIC_ANSWER_TOKEN
    assert token_transport.requests[0].headers["host"] == TOKEN_HOST
    assert push_transport.requests[0].url.host == PUBLIC_ANSWER
    assert push_transport.requests[0].headers["host"] == FHIR_HOST


# --- 3. the assertion ---------------------------------------------------------------


def test_the_assertion_carries_exactly_the_smart_claims() -> None:
    sender, _, token_transport = smart_sender()
    sender.send(smart_push(), payload())
    form = form_of(token_transport.requests[0])
    assert form["grant_type"] == "client_credentials"
    assert form["client_assertion_type"] == ASSERTION_TYPE
    assert form["scope"] == SMART_SCOPE
    header, claims, signature = assertion_of(token_transport.requests[0])
    assert header["alg"] == "ES384" and header["typ"] == "JWT"
    assert claims["iss"] == claims["sub"]
    assert set(claims) == {"iss", "sub", "aud", "exp", "jti"}
    assert signature != b""


def test_the_audience_is_the_registered_token_endpoint_and_nothing_else() -> None:
    sender, _, token_transport = smart_sender()
    sender.send(smart_push(), payload())
    _, claims, _ = assertion_of(token_transport.requests[0])
    assert claims["aud"] == f"https://{TOKEN_HOST}/oauth2/token"


def test_the_assertion_expiry_is_clamped_by_the_share_consent_expiry() -> None:
    """"Scoped by share consent token", made enforceable by the hospital.

    files/06 §2.1 gives a share grant ``{recipient, visit, sections,
    expiry}``. The expiry is the half a connector can act on, so the
    credential we present to the hospital's authorization server is valid only
    inside it: the assertion's ``exp`` is the earlier of our own short ceiling
    and the consent's own end. A stale-consent authorization is then refused
    by the *receiver's* clock, not only by ours.
    """
    soon = datetime.now(UTC) + timedelta(seconds=20)
    sender, _, token_transport = smart_sender(consent=granted_until(soon))
    sender.send(smart_push(), payload())
    _, claims, _ = assertion_of(token_transport.requests[0])
    assert int(claims["exp"]) <= int(soon.timestamp())  # type: ignore[call-overload]


def test_a_consent_without_an_expiry_still_gets_the_short_ceiling() -> None:
    before = datetime.now(UTC)
    sender, _, token_transport = smart_sender(consent=granted_until(None))
    sender.send(smart_push(), payload())
    _, claims, _ = assertion_of(token_transport.requests[0])
    assert int(claims["exp"]) <= int((before + timedelta(seconds=61)).timestamp())  # type: ignore[call-overload]


def test_a_consent_that_has_already_expired_never_reaches_the_token_endpoint() -> None:
    stale = datetime.now(UTC) - timedelta(seconds=1)
    sender, push_transport, token_transport = smart_sender(consent=granted_until(stale))
    receipt = sender.send(smart_push(), payload())
    assert receipt.state is ReceiptState.FAILED
    assert receipt.outcome_code == "smart_consent_expired"
    assert token_transport.requests == [] and push_transport.requests == []


def test_no_token_is_requested_for_a_push_the_consent_gate_refused() -> None:
    sender, push_transport, token_transport = smart_sender(consent=refused)
    with pytest.raises(ConsentDenied):
        sender.send(smart_push(), payload())
    assert token_transport.requests == [] and push_transport.requests == []


def test_two_pushes_mint_two_assertions_and_never_reuse_a_jti() -> None:
    sender, _, token_transport = smart_sender()
    sender.send(smart_push(), payload())
    sender.send(smart_push(resource_ref="note-100"), ClinicalPayload(body=b"{}", media_type=FHIR_JSON))
    first, second = (assertion_of(request)[1] for request in token_transport.requests)
    assert first["jti"] != second["jti"]


def test_the_access_token_is_minted_per_push_and_never_cached() -> None:
    sender, push_transport, token_transport = smart_sender()
    sender.send(smart_push(), payload())
    sender.send(smart_push(resource_ref="note-100"), ClinicalPayload(body=b"{}", media_type=FHIR_JSON))
    assert len(token_transport.requests) == 2, "a cached token outlives its consent check"
    assert len(push_transport.requests) == 2


def test_an_rsa_key_signs_rs384_and_a_p384_key_signs_es384() -> None:
    for pem, expected in (
        (smart_key_pem(rsa_bits=2048), "RS384"),
        (smart_key_pem(), "ES384"),
    ):
        sender, _, token_transport = smart_sender(
            credential_resolver=smart_credentials(private_key=pem)
        )
        sender.send(smart_push(), payload())
        header, _, _ = assertion_of(token_transport.requests[0])
        assert header["alg"] == expected


def test_a_key_smart_does_not_permit_is_refused_before_anything_leaves() -> None:
    """SMART names RS384 and ES384. A P-256 key is perfectly good crypto and
    is still not one of them, so it fails closed rather than being signed with
    the nearest available curve."""
    sender, push_transport, token_transport = smart_sender(
        credential_resolver=smart_credentials(private_key=smart_key_pem(curve=ec.SECP256R1()))
    )
    receipt = sender.send(smart_push(), payload())
    assert receipt.state is ReceiptState.FAILED
    assert receipt.outcome_code == "smart_key_unsupported"
    assert token_transport.requests == [] and push_transport.requests == []


def test_a_registered_key_id_travels_in_the_jose_header() -> None:
    sender, _, token_transport = smart_sender(
        credential_resolver=smart_credentials(key_id="fixture-key-name")
    )
    sender.send(smart_push(), payload())
    header, _, _ = assertion_of(token_transport.requests[0])
    assert header["kid"] == "fixture-key-name"


# --- 4. the token response, which is a credential and not a record ------------------


def test_the_granted_token_reaches_the_push_and_appears_nowhere_else() -> None:
    sender, push_transport, token_transport = smart_sender()
    receipt = sender.send(smart_push(), payload())
    assert push_transport.requests[0].headers["authorization"] == f"Bearer {FAKE_ACCESS_TOKEN}"
    assert "authorization" not in token_transport.requests[0].headers
    assert FAKE_ACCESS_TOKEN not in repr(receipt)


def test_a_grant_that_does_not_cover_the_request_stops_the_push() -> None:
    def narrower(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"access_token": "x", "token_type": "bearer", "scope": "system/Patient.r"},
        )

    sender, push_transport, _ = smart_sender(token_handler=narrower)
    receipt = sender.send(smart_push(), payload())
    assert receipt.outcome_code == "smart_scope_not_granted"
    assert push_transport.requests == []


@pytest.mark.parametrize(
    ("granted_scope", "sends"),
    [
        ("system/Bundle.c", True),
        ("system/Bundle.cruds", True),
        ("system/*.c", True),
        ("system/Patient.r system/Bundle.c", True),
        ("system/Bundle.r", False),
        ("system/Patient.c", False),
        ("user/Bundle.c", False),
    ],
)
def test_the_granted_scope_must_cover_the_scope_we_asked_for(
    granted_scope: str, sends: bool
) -> None:
    def answer(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"access_token": "x", "token_type": "bearer", "scope": granted_scope},
        )

    sender, push_transport, _ = smart_sender(token_handler=answer)
    sender.send(smart_push(), payload())
    assert bool(push_transport.requests) is sends


def test_a_response_that_omits_the_scope_is_the_scope_we_asked_for() -> None:
    """RFC 6749 §5.1: an omitted ``scope`` means the grant is identical to the
    request. Treating silence as a denial would break conformant servers;
    treating it as a wildcard would be the opposite mistake."""

    def silent(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"access_token": "x", "token_type": "bearer"})

    sender, push_transport, _ = smart_sender(token_handler=silent)
    assert sender.send(smart_push(), payload()).state is ReceiptState.DELIVERED
    assert len(push_transport.requests) == 1


@pytest.mark.parametrize(
    ("handler_body", "expected"),
    [
        ({"token_type": "bearer"}, "smart_token_malformed"),
        ({"access_token": "x", "token_type": "mac"}, "smart_token_type_unsupported"),
        ({"access_token": "  ", "token_type": "bearer"}, "smart_token_malformed"),
        ({"access_token": "a b", "token_type": "bearer"}, "smart_token_malformed"),
    ],
)
def test_a_token_response_that_is_not_a_bearer_token_stops_the_push(
    handler_body: dict[str, str], expected: str
) -> None:
    def answer(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=handler_body)

    sender, push_transport, _ = smart_sender(token_handler=answer)
    receipt = sender.send(smart_push(), payload())
    assert receipt.outcome_code == expected
    assert push_transport.requests == []


def test_a_malformed_token_response_names_none_of_its_bytes() -> None:
    def rubbish(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>giris yapin Ayse Yilmaz</html>")

    sender, _, _ = smart_sender(token_handler=rubbish)
    receipt = sender.send(smart_push(), payload())
    assert receipt.outcome_code == "smart_token_response_malformed"
    assert "Ayse" not in repr(receipt)


def test_the_token_response_body_is_bounded() -> None:
    def enormous(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"{" + b" " * 200_000 + b"}")

    sender, push_transport, _ = smart_sender(token_handler=enormous)
    receipt = sender.send(smart_push(), payload())
    assert receipt.outcome_code == "smart_token_response_too_large"
    assert push_transport.requests == []


def test_an_authorization_server_error_body_is_not_read_at_all() -> None:
    """The status is the diagnosis. 400 is our assertion, 401 is our client
    identity, 5xx is theirs — and none of those needs a sentence from them."""

    def denied(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400, json={"error": "invalid_client", "error_description": "hasta Ayse Yilmaz"}
        )

    sender, push_transport, _ = smart_sender(token_handler=denied)
    receipt = sender.send(smart_push(), payload())
    assert receipt.outcome_code == "smart_token_http_400"
    assert "Ayse" not in repr(receipt)
    assert push_transport.requests == []


def test_a_token_endpoint_failure_is_always_a_definite_non_delivery() -> None:
    """The push never happened, so there is nothing ambiguous to park: a
    failed exchange can never produce an ``unresolved`` receipt, whatever the
    receiver's idempotency declaration says."""

    def unavailable(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    for declaration in ("honoured_per_dpa", "not_declared"):
        sender, push_transport, _ = smart_sender(
            token_handler=unavailable,
            destinations=[smart_destination(receiver_idempotency=declaration)],
        )
        receipt = sender.send(smart_push(), payload())
        assert receipt.state is ReceiptState.FAILED
        assert receipt.outcome_code == "smart_token_http_503"
        assert push_transport.requests == []


def test_a_token_transport_failure_is_a_non_delivery_too() -> None:
    def dropped(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    sender, push_transport, _ = smart_sender(token_handler=dropped)
    receipt = sender.send(smart_push(), payload())
    assert receipt.state is ReceiptState.FAILED
    assert receipt.outcome_code == "smart_token_unreachable"
    assert push_transport.requests == []


def test_the_access_token_never_renders_itself() -> None:
    from intake_connectors.smart import AccessToken

    token = AccessToken("fixture-access-value")
    assert "fixture-access-value" not in repr(token)
    assert "fixture-access-value" not in f"{token}"
    assert token.value == "fixture-access-value"


# --- 5. the framework headers an adapter may not overwrite --------------------------


def test_an_adapter_cannot_overwrite_the_framework_headers() -> None:
    """An adapter is per-hospital code. Letting it set ``Authorization`` or
    ``Idempotency-Key`` would let one swap the credential or forge a replay,
    so the framework's headers are applied last and win."""
    from intake_connectors.fhir import FhirR4PushAdapter
    from intake_connectors.adapter import OutboundCall

    class GreedyAdapter(FhirR4PushAdapter):
        def build(self, destination: object, payload_: object) -> OutboundCall:
            call = super().build(destination, payload_)  # type: ignore[arg-type]
            return OutboundCall(
                method=call.method,
                path=call.path,
                media_type=call.media_type,
                body=call.body,
                headers={
                    "Authorization": "Bearer stolen",
                    "Idempotency-Key": "ik-forged",
                    "Content-Type": "text/plain",
                    "Prefer": "return=representation",
                },
            )

    sender, push_transport, _ = smart_sender(adapters=[GreedyAdapter()])
    receipt = sender.send(smart_push(), payload())
    sent = push_transport.requests[0].headers
    assert sent["authorization"] == f"Bearer {FAKE_ACCESS_TOKEN}"
    assert sent["idempotency-key"] == receipt.idempotency_key
    assert sent["content-type"] == FHIR_JSON
