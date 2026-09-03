"""INT-180 — Keycloak access-token verification (files/08 §2; ADR-017).

The verifier is hand-written over ``cryptography`` on the same terms as
``intake_api.dpop``: one algorithm, no negotiation. That decision is only
worth anything if the negatives are tested, so most of this file is negatives
— ``alg: none``, an HMAC swapped in for RS256, an unknown ``kid``, a tampered
payload, a foreign issuer, a wrong audience, an expired token.

No network and no committed key material: the key pair is generated in-process
for the test run, so nothing here is a secret that could be reused anywhere.
"""

from __future__ import annotations

import base64
import json
import time
from collections.abc import Mapping
from typing import Any

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from intake_platform.admin.oidc import KeycloakClaimsVerifier, load_jwks
from intake_platform.admin.principal import ClaimsRejected, principal_from_claims

ISSUER = "http://localhost:8080/realms/intake-dev"
AUDIENCE = "api"
KID = "int180-unit-lane"
NOW = 1_800_000_000

_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def jwks_document(kid: str = KID) -> dict[str, Any]:
    numbers = _PRIVATE_KEY.public_key().public_numbers()
    return {
        "keys": [
            {
                "kid": kid,
                "kty": "RSA",
                "use": "sig",
                "alg": "RS256",
                "n": _b64(numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big")),
                "e": _b64(numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, "big")),
            }
        ]
    }


def claims(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "kc-sub-clinical-lead",
        "sid": "sid-clinical-lead-1",
        "org": "org:intake",
        "tenant": "tenant-a",
        "aaguid": "00000000-0000-0000-0000-000000000000",
        "credential_id": "cred-clinical-lead-1",
        "realm_access": {"roles": ["clinical_lead"]},
        "exp": NOW + 600,
        "nbf": NOW - 10,
    }
    payload.update(overrides)
    return payload


def token(
    payload: Mapping[str, Any] | None = None,
    *,
    header: Mapping[str, Any] | None = None,
    signature: bytes | None = None,
) -> str:
    head = _b64(json.dumps(dict(header or {"alg": "RS256", "kid": KID, "typ": "JWT"})).encode())
    body = _b64(json.dumps(dict(payload if payload is not None else claims())).encode())
    signing_input = f"{head}.{body}".encode("ascii")
    signed = (
        signature
        if signature is not None
        else _PRIVATE_KEY.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    )
    return f"{head}.{body}.{_b64(signed)}"


def verifier(**overrides: Any) -> KeycloakClaimsVerifier:
    settings: dict[str, Any] = {
        "issuer": ISSUER,
        "audience": AUDIENCE,
        "keys": load_jwks(jwks_document()),
        "clock": lambda: NOW,
    }
    settings.update(overrides)
    return KeycloakClaimsVerifier(**settings)


class TestJwks:
    def test_an_rsa_signing_key_loads_under_its_kid(self) -> None:
        keys = load_jwks(jwks_document())
        assert set(keys) == {KID}

    def test_keys_the_verifier_could_not_use_are_dropped(self) -> None:
        document = jwks_document()
        document["keys"].append({"kid": "ec", "kty": "EC", "use": "sig"})
        document["keys"].append({"kid": "enc", "kty": "RSA", "use": "enc"})
        document["keys"].append({"kid": "hs", "kty": "RSA", "alg": "HS256"})
        assert set(load_jwks(document)) == {KID}

    def test_an_empty_key_set_is_a_configuration_error(self) -> None:
        with pytest.raises(ValueError):
            load_jwks({"keys": []})


class TestHappyPath:
    def test_a_well_formed_token_yields_its_claims_and_a_principal(self) -> None:
        verified = verifier().verify(token())
        assert verified["sub"] == "kc-sub-clinical-lead"
        principal = principal_from_claims(verified, source_ip="192.0.2.10")
        assert principal.tenant == "tenant-a"

    def test_a_list_audience_containing_ours_is_accepted(self) -> None:
        assert verifier().verify(token(claims(aud=["account", AUDIENCE])))

    def test_a_token_inside_the_skew_window_is_accepted(self) -> None:
        assert verifier(clock=lambda: NOW + 700).verify(token())


class TestNegatives:
    @pytest.mark.parametrize(
        "header",
        [
            {"alg": "none", "kid": KID},
            {"alg": "HS256", "kid": KID},
            {"alg": "RS512", "kid": KID},
            {"kid": KID},
        ],
        ids=["none", "hs256", "rs512", "absent"],
    )
    def test_every_algorithm_but_rs256_is_refused(self, header: dict[str, Any]) -> None:
        with pytest.raises(ClaimsRejected):
            verifier().verify(token(header=header))

    def test_an_unknown_kid_is_refused(self) -> None:
        with pytest.raises(ClaimsRejected):
            verifier().verify(token(header={"alg": "RS256", "kid": "rotated-away"}))

    def test_a_tampered_payload_is_refused(self) -> None:
        head, body, signature = token().split(".")
        forged = _b64(json.dumps(claims(sub="kc-sub-platform-owner")).encode())
        with pytest.raises(ClaimsRejected):
            verifier().verify(f"{head}.{forged}.{signature}")

    def test_a_garbage_signature_is_refused(self) -> None:
        with pytest.raises(ClaimsRejected):
            verifier().verify(token(signature=b"\x00" * 256))

    def test_a_foreign_issuer_is_refused(self) -> None:
        with pytest.raises(ClaimsRejected):
            verifier().verify(token(claims(iss="https://issuer.invalid/realms/other")))

    def test_a_wrong_audience_is_refused(self) -> None:
        with pytest.raises(ClaimsRejected):
            verifier().verify(token(claims(aud="account")))

    def test_an_expired_token_is_refused(self) -> None:
        with pytest.raises(ClaimsRejected):
            verifier(clock=lambda: NOW + 10_000).verify(token())

    def test_a_token_with_no_expiry_is_refused(self) -> None:
        payload = claims()
        del payload["exp"]
        with pytest.raises(ClaimsRejected):
            verifier().verify(token(payload))

    def test_a_not_yet_valid_token_is_refused(self) -> None:
        with pytest.raises(ClaimsRejected):
            verifier().verify(token(claims(nbf=NOW + 10_000)))

    @pytest.mark.parametrize(
        "malformed",
        ["", "a.b", "a.b.c.d", "!!!.!!!.!!!", "a." + _b64(b"[]") + ".c"],
    )
    def test_a_malformed_token_is_refused_rather_than_raising(self, malformed: str) -> None:
        with pytest.raises(ClaimsRejected):
            verifier().verify(malformed)

    def test_an_oversized_token_is_refused_before_parsing(self) -> None:
        with pytest.raises(ClaimsRejected):
            verifier().verify("x" * 9000)


class TestEnvWiring:
    """``_admin_from_env`` — all three of issuer, audience and a mirrored
    JWKS, or the console stays unconfigured and every route answers 503."""

    def _write_jwks(self, tmp_path: Any, document: dict[str, Any]) -> str:
        path = tmp_path / "jwks.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        return str(path)

    def _set(self, monkeypatch: pytest.MonkeyPatch, **env: str) -> None:
        for name in (
            "INTAKE_ADMIN_OIDC_ISSUER",
            "INTAKE_ADMIN_OIDC_AUDIENCE",
            "INTAKE_ADMIN_OIDC_JWKS_PATH",
            "INTAKE_ADMIN_IP_ALLOWLIST",
        ):
            monkeypatch.delenv(name, raising=False)
        for name, value in env.items():
            monkeypatch.setenv(name, value)

    def test_no_environment_leaves_the_console_unconfigured(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from intake_api.app import _admin_from_env

        self._set(monkeypatch)
        assert _admin_from_env() is None

    def test_a_partial_environment_leaves_it_unconfigured(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        from intake_api.app import _admin_from_env

        self._set(
            monkeypatch,
            INTAKE_ADMIN_OIDC_ISSUER=ISSUER,
            INTAKE_ADMIN_OIDC_JWKS_PATH=self._write_jwks(tmp_path, jwks_document()),
        )
        assert _admin_from_env() is None

    def test_a_complete_environment_wires_a_verifier_and_an_empty_allowlist(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        from intake_api.app import _admin_from_env

        self._set(
            monkeypatch,
            INTAKE_ADMIN_OIDC_ISSUER=ISSUER,
            INTAKE_ADMIN_OIDC_AUDIENCE=AUDIENCE,
            INTAKE_ADMIN_OIDC_JWKS_PATH=self._write_jwks(tmp_path, jwks_document()),
        )
        wiring = _admin_from_env()
        assert wiring is not None
        # the env-built verifier holds the real clock, so the token is dated
        # against it rather than against the suite's frozen NOW
        real_now = int(time.time())
        live = token(claims(exp=real_now + 600, nbf=real_now - 10))
        assert wiring.claims.verify(live)["sub"] == "kc-sub-clinical-lead"
        # files/08 §2.3 names no range, so the shipping allow-list is empty
        # and admits nobody (invariant 17)
        assert wiring.ip_allowlist.networks == ()
        assert not wiring.ip_allowlist.permits("192.0.2.10")
        # and the tenant deployment map is empty, so break-glass refuses
        # every tenant until §2.6's question is answered per tenant
        assert dict(wiring.deployments) == {}

    def test_an_allowlist_from_the_environment_is_parsed(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        from intake_api.app import _admin_from_env

        self._set(
            monkeypatch,
            INTAKE_ADMIN_OIDC_ISSUER=ISSUER,
            INTAKE_ADMIN_OIDC_AUDIENCE=AUDIENCE,
            INTAKE_ADMIN_OIDC_JWKS_PATH=self._write_jwks(tmp_path, jwks_document()),
            INTAKE_ADMIN_IP_ALLOWLIST="192.0.2.0/24",
        )
        wiring = _admin_from_env()
        assert wiring is not None
        assert wiring.ip_allowlist.permits("192.0.2.10")

    @pytest.mark.parametrize("document", [{"keys": []}, {"not": "a jwks"}])
    def test_an_unusable_key_set_leaves_it_unconfigured(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any, document: dict[str, Any]
    ) -> None:
        from intake_api.app import _admin_from_env

        self._set(
            monkeypatch,
            INTAKE_ADMIN_OIDC_ISSUER=ISSUER,
            INTAKE_ADMIN_OIDC_AUDIENCE=AUDIENCE,
            INTAKE_ADMIN_OIDC_JWKS_PATH=self._write_jwks(tmp_path, document),
        )
        assert _admin_from_env() is None

    def test_an_absent_jwks_file_leaves_it_unconfigured(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        from intake_api.app import _admin_from_env

        self._set(
            monkeypatch,
            INTAKE_ADMIN_OIDC_ISSUER=ISSUER,
            INTAKE_ADMIN_OIDC_AUDIENCE=AUDIENCE,
            INTAKE_ADMIN_OIDC_JWKS_PATH=str(tmp_path / "never-mirrored.json"),
        )
        assert _admin_from_env() is None
