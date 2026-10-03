"""Record a real Keycloak WebAuthn login through the INT-378 provider, and the stock control.

INT-378. The admin console needs ``aaguid`` and ``credential_id`` in a staff token. This script
logs a synthetic staff account in to a running Keycloak twice, through the committed realm
(``intake-dev``, whose WebAuthn execution is ``intake-webauthn-session-notes``) and through its
stock twin (``intake-dev-stock``, identical except that the execution is Keycloak's own
``webauthn-authenticator``). It writes what each login produced to
``tests/admin/fixtures/keycloak_webauthn_login.json``, which
``tests/admin/test_webauthn_session_notes_provider.py`` replays through the console.

The Keycloak must already run, with the provider jar in ``providers/`` and both realms imported;
``docs/evidence/INT-378.md`` records the exact commands. Nothing here starts a container.

**The authenticator is software.** A P-256 key is generated for the run and discarded with it.
Its public key, a random credential id and a random AAGUID are stored on the account through the
admin API as an ordinary WebAuthn credential (``RepresentationToModel.createCredentials`` hands a
credential without a value to ``createCredentialThroughProvider``). The assertion is then built
the way a browser builds one (WebAuthn §7.2: ``authenticatorData`` is the RP id hash, the UP and
UV flags and a counter; the signature covers ``authenticatorData || SHA-256(clientDataJSON)``)
and posted to the real login form. Keycloak verifies it with webauthn4j, exactly as for a
hardware key.

Every value is synthetic: the account is ``int378-staff``, its mail is ``.invalid``, and the
AAGUID names no authenticator model. The admin password comes from the environment, never from
this file.

Usage (Keycloak on 127.0.0.1:18085, bootstrap admin ``int378-admin``)::

    KC_ADMIN_PASSWORD=... uv run python scripts/keycloak/record_webauthn_login.py \\
        --base-url http://127.0.0.1:18085 --jar-sha256 <sha256> --dist-sha256 <sha256>
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import os
import re
import secrets
import struct
import sys
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "packages" / "intake_platform" / "src"))

from intake_platform.admin.oidc import KeycloakClaimsVerifier, load_jwks  # noqa: E402
from intake_platform.admin.principal import (  # noqa: E402
    _ID_SHAPE,
    ClaimsRejected,
    PrincipalRefused,
    principal_from_claims,
)

REALM_FILE = REPO / "infra" / "keycloak" / "dev-realm.json"
OUT = REPO / "tests" / "admin" / "fixtures" / "keycloak_webauthn_login.json"

CLIENT_ID = "admin-web"
REDIRECT_URI = "http://localhost:3000/int378"
AUDIENCE = "api"
USERNAME = "int378-staff"
ROLE = "tenant_clinical_responsible"  # files/08 §2.1: reaches patient content, so needs hwk
ORG = "org-int378"
REALMS = {
    "intake-webauthn-session-notes": "intake-dev",
    "webauthn-authenticator": "intake-dev-stock",
}

_FORM_ACTION = re.compile(r'<form[^>]*id="{form_id}"[^>]*action="([^"]+)"')
#: The WebAuthn page's parameters, quoted with ' (26.1.4's theme) or " (26.7.4's keycloak.v2).
_JS_FIELD = re.compile(r"""(\w+)\s*:\s*(?:'([^']*)'|"([^"]*)")""")


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def b64url_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def cbor_cose_es256(key: ec.EllipticCurvePublicKey) -> bytes:
    """The COSE_Key (RFC 9053 §7.1.1) of a P-256 key, as the fixed five-entry CBOR map a
    WebAuthn authenticator emits: {1: 2, 3: -7, -1: 1, -2: x, -3: y}."""
    numbers = key.public_numbers()
    x = numbers.x.to_bytes(32, "big")
    y = numbers.y.to_bytes(32, "big")
    return (
        b"\xa5"  # map(5)
        + b"\x01\x02"  # kty: EC2
        + b"\x03\x26"  # alg: -7 (ES256)
        + b"\x20\x01"  # crv: P-256
        + b"\x21\x58\x20"
        + x  # x: bstr(32)
        + b"\x22\x58\x20"
        + y  # y: bstr(32)
    )


@dataclass(frozen=True)
class SoftwareAuthenticator:
    key: ec.EllipticCurvePrivateKey
    credential_id: bytes
    aaguid: str

    @classmethod
    def generate(cls) -> SoftwareAuthenticator:
        # a credential id whose base64url form starts with a letter or digit: the console's id
        # shape refuses a leading '-' or '_' (reported in docs/evidence/INT-378.md)
        while True:
            credential_id = secrets.token_bytes(32)
            if _ID_SHAPE.fullmatch(b64url(credential_id)):
                break
        return cls(ec.generate_private_key(ec.SECP256R1()), credential_id, str(uuid.uuid4()))

    def stored_credential(self) -> dict[str, Any]:
        """The CredentialRepresentation Keycloak keeps for a registered WebAuthn key
        (WebAuthnCredentialProvider.getCredentialModelFromCredentialInput)."""
        data = {
            "aaguid": self.aaguid,
            "credentialId": base64.b64encode(self.credential_id).decode("ascii"),
            "counter": 0,
            "attestationStatement": None,
            "credentialPublicKey": b64url(cbor_cose_es256(self.key.public_key())),
            "attestationStatementFormat": "none",
            "transports": [],
        }
        return {
            "type": "webauthn",
            "userLabel": "int378 software key",
            "credentialData": json.dumps(data),
            "secretData": "{}",
        }

    def assert_for(self, *, challenge: str, rp_id: str, origin: str) -> dict[str, str]:
        client_data = json.dumps(
            {
                "type": "webauthn.get",
                "challenge": challenge,
                "origin": origin,
                "crossOrigin": False,
            },
            separators=(",", ":"),
        ).encode("utf-8")
        flags = 0x01 | 0x04  # UP | UV: the realm requires user verification
        authenticator_data = (
            hashlib.sha256(rp_id.encode("utf-8")).digest() + bytes([flags]) + struct.pack(">I", 1)
        )
        signature = self.key.sign(
            authenticator_data + hashlib.sha256(client_data).digest(), ec.ECDSA(hashes.SHA256())
        )
        return {
            "clientDataJSON": b64url(client_data),
            "authenticatorData": b64url(authenticator_data),
            "signature": b64url(signature),
            "credentialId": b64url(self.credential_id),
            "userHandle": "",
            "error": "",
        }


def form_action(page: str, form_id: str) -> str:
    match = re.search(_FORM_ACTION.pattern.format(form_id=form_id), page)
    if match is None:
        raise RuntimeError(f"the page has no form {form_id!r}")
    return html.unescape(match.group(1))


def admin_token(http: httpx.Client, password: str) -> str:
    response = http.post(
        "/realms/master/protocol/openid-connect/token",
        data={
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": "int378-admin",
            "password": password,
        },
    )
    response.raise_for_status()
    token: str = response.json()["access_token"]
    return token


def server_version(http: httpx.Client, bearer: str) -> str:
    """The version the running server reports, so a recording names the Keycloak it ran on."""
    response = http.get("/admin/serverinfo", headers={"Authorization": f"Bearer {bearer}"})
    response.raise_for_status()
    version: str = response.json()["systemInfo"]["version"]
    return version


def create_staff_account(
    http: httpx.Client, realm: str, bearer: str, key: SoftwareAuthenticator, tenant: str
) -> str:
    headers = {"Authorization": f"Bearer {bearer}"}
    password = f"dev-only-{secrets.token_urlsafe(12)}"
    user = {
        "username": USERNAME,
        "enabled": True,
        "firstName": "Synthetic",
        "lastName": "Staff",
        "email": f"{USERNAME}@intake.invalid",
        "emailVerified": True,
        "attributes": {"org": [ORG], "tenant": [tenant]},
        "credentials": [
            {"type": "password", "value": password, "temporary": False},
            key.stored_credential(),
        ],
    }
    # a rerun replaces the synthetic account, so every recording starts from a fresh credential
    existing = http.get(
        f"/admin/realms/{realm}/users",
        params={"username": USERNAME, "exact": "true"},
        headers=headers,
    )
    existing.raise_for_status()
    for stale in existing.json():
        http.delete(
            f"/admin/realms/{realm}/users/{stale['id']}", headers=headers
        ).raise_for_status()
    created = http.post(f"/admin/realms/{realm}/users", json=user, headers=headers)
    created.raise_for_status()
    user_id = created.headers["location"].rsplit("/", 1)[1]
    role = http.get(f"/admin/realms/{realm}/roles/{ROLE}", headers=headers)
    role.raise_for_status()
    http.post(
        f"/admin/realms/{realm}/users/{user_id}/role-mappings/realm",
        json=[role.json()],
        headers=headers,
    ).raise_for_status()
    return password


class Browser:
    """Keeps cookies the way a browser does on a loopback origin.

    Keycloak marks its login cookies ``Secure``. A browser still sends them to
    ``http://127.0.0.1`` (a loopback origin is a secure context); httpx does not, and Keycloak
    then answers the password post with ``cookie_not_found``.
    """

    def __init__(self, base_url: str) -> None:
        self._http = httpx.Client(base_url=base_url, follow_redirects=False, timeout=30)
        self._jar: dict[str, str] = {}

    def __enter__(self) -> Browser:
        return self

    def __exit__(self, *exc: object) -> None:
        self._http.close()

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        headers = dict(kwargs.pop("headers", None) or {})
        if self._jar:
            headers["Cookie"] = "; ".join(f"{name}={value}" for name, value in self._jar.items())
        response = self._http.request(method, url, headers=headers, **kwargs)
        self._http.cookies.clear()
        for line in response.headers.get_list("set-cookie"):
            pair, *attributes = line.split(";")
            name, _, value = pair.strip().partition("=")
            if not value or any(a.strip().lower() == "max-age=0" for a in attributes):
                self._jar.pop(name, None)
            else:
                self._jar[name] = value
        return response

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("POST", url, **kwargs)


def log_in(
    http: Browser, base_url: str, realm: str, password: str, key: SoftwareAuthenticator
) -> dict[str, Any]:
    verifier_code = b64url(secrets.token_bytes(32))
    challenge = b64url(hashlib.sha256(verifier_code.encode("ascii")).digest())
    query = urlencode(
        {
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "response_type": "code",
            "scope": "openid",
            "state": secrets.token_urlsafe(8),
            "nonce": secrets.token_urlsafe(8),
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    login_page = http.get(f"/realms/{realm}/protocol/openid-connect/auth?{query}")
    login_page.raise_for_status()
    webauthn_page = http.post(
        form_action(login_page.text, "kc-form-login"),
        data={"username": USERNAME, "password": password, "credentialId": ""},
    )
    webauthn_page.raise_for_status()
    found = _JS_FIELD.findall(webauthn_page.text)
    fields = {name: single or double for name, single, double in found}
    if fields.get("userVerification") != "required":
        raise RuntimeError("the WebAuthn page does not require user verification")
    assertion = key.assert_for(
        challenge=fields["challenge"], rp_id=fields["rpId"], origin=base_url.rstrip("/")
    )
    redirected = http.post(form_action(webauthn_page.text, "webauth"), data=assertion)
    if redirected.status_code != 302:
        raise RuntimeError(f"the WebAuthn assertion was not accepted ({redirected.status_code})")
    code = parse_qs(urlparse(redirected.headers["location"]).query)["code"][0]
    tokens = http.post(
        f"/realms/{realm}/protocol/openid-connect/token",
        data={
            "grant_type": "authorization_code",
            "client_id": CLIENT_ID,
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": verifier_code,
        },
    )
    tokens.raise_for_status()
    access_token: str = tokens.json()["access_token"]
    jwks = http.get(f"/realms/{realm}/protocol/openid-connect/certs")
    jwks.raise_for_status()
    verifier = KeycloakClaimsVerifier(
        issuer=f"{base_url.rstrip('/')}/realms/{realm}",
        audience=AUDIENCE,
        keys=load_jwks(jwks.json()),
    )
    claims = dict(verifier.verify(access_token))  # signature, issuer, audience, expiry: live
    try:
        principal = principal_from_claims(claims, source_ip="127.0.0.1")
    except (ClaimsRejected, PrincipalRefused) as refused:
        console = {"admitted": False, "refusal": type(refused).__name__, "reason": str(refused)}
    else:
        console = {
            "admitted": True,
            "aaguid": principal.authenticator_aaguid,
            "credential_id": principal.credential_id,
            "tenant": principal.tenant,
            "roles": sorted(role.value for role in principal.roles),
        }
    return {"access_token_claims": claims, "console": console}


def realm_sha256() -> str:
    return hashlib.sha256(REALM_FILE.read_bytes()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default="http://127.0.0.1:18085")
    parser.add_argument("--jar-sha256", required=True)
    parser.add_argument("--dist-sha256", required=True)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    password = os.environ["KC_ADMIN_PASSWORD"]
    key = SoftwareAuthenticator.generate()
    tenant = str(uuid.uuid4())
    logins: dict[str, Any] = {}
    with httpx.Client(base_url=args.base_url, follow_redirects=False, timeout=30) as admin:
        bearer = admin_token(admin, password)
        version = server_version(admin, bearer)
        for authenticator, realm in REALMS.items():
            staff_password = create_staff_account(admin, realm, bearer, key, tenant)
            with Browser(args.base_url) as http:
                logins[authenticator] = {
                    "realm": realm,
                    **log_in(http, args.base_url, realm, staff_password, key),
                }
    record: Mapping[str, Any] = {
        "recorded_by": "scripts/keycloak/record_webauthn_login.py (INT-378)",
        "keycloak": {"version": version, "dist_sha256": args.dist_sha256},
        "provider_jar_sha256": args.jar_sha256,
        "realm_file_sha256": realm_sha256(),
        "software_authenticator": {
            "aaguid": key.aaguid,
            "credential_id": b64url(key.credential_id),
        },
        "logins": logins,
    }
    args.out.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
