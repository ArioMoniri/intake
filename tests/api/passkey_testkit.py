"""INT-582 test kit: a software platform authenticator that speaks WebAuthn's
JSON shapes exactly as react-native-passkeys hands them to the API.

It is a test double for the PHONE, not for the verifier: it builds real
clientDataJSON, real authenticator data and a real ES256 signature over them
with a fresh P-256 key, so the verifier under test runs every check on bytes a
genuine authenticator would produce. Each near miss is one knob here
(an origin, an RP ID, a flag, a counter, a format), never a hand-edited blob.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import Any

import cbor2
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

RP_ID = "3-211-2-143.sslip.io"
ORIGIN = f"https://{RP_ID}"

FLAG_UP = 0x01
FLAG_UV = 0x04
FLAG_BE = 0x08
FLAG_BS = 0x10
FLAG_AT = 0x40
FLAG_ED = 0x80


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def unb64url(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


@dataclass
class Authenticator:
    """One passkey on one phone. ``counter`` is what the next ceremony reports
    (a synced Apple passkey reports 0 forever); ``backed_up`` sets BE and BS."""

    rp_id: str = RP_ID
    counter: int = 0
    backed_up: bool = True
    key: ec.EllipticCurvePrivateKey = field(
        default_factory=lambda: ec.generate_private_key(ec.SECP256R1())
    )
    credential_id: bytes = field(default_factory=lambda: os.urandom(20))
    user_handle: bytes | None = None

    # --- pieces -------------------------------------------------------------------------

    def cose_key(self, *, alg: int = -7, extra: dict[int, Any] | None = None) -> bytes:
        numbers = self.key.public_key().public_numbers()
        cose: dict[int, Any] = {
            1: 2,
            3: alg,
            -1: 1,
            -2: numbers.x.to_bytes(32, "big"),
            -3: numbers.y.to_bytes(32, "big"),
        }
        cose.update(extra or {})
        return cbor2.dumps(cose)

    def client_data(
        self,
        ceremony: str,
        challenge: str,
        *,
        origin: str = ORIGIN,
        cross_origin: object = None,
        extra: dict[str, Any] | None = None,
    ) -> bytes:
        data: dict[str, Any] = {"type": ceremony, "challenge": challenge, "origin": origin}
        if cross_origin is not None:
            data["crossOrigin"] = cross_origin
        data.update(extra or {})
        return json.dumps(data, separators=(",", ":")).encode("utf-8")

    def flags(self, *, up: bool, uv: bool, attested: bool) -> int:
        value = (FLAG_UP if up else 0) | (FLAG_UV if uv else 0) | (FLAG_AT if attested else 0)
        if self.backed_up:
            value |= FLAG_BE | FLAG_BS
        return value

    def auth_data(
        self,
        *,
        attested: bool,
        rp_id: str | None = None,
        up: bool = True,
        uv: bool = True,
        flags: int | None = None,
        counter: int | None = None,
        cose: bytes | None = None,
        credential_id: bytes | None = None,
        trailing: bytes = b"",
    ) -> bytes:
        rp_hash = hashlib.sha256((rp_id or self.rp_id).encode("ascii")).digest()
        value = self.flags(up=up, uv=uv, attested=attested) if flags is None else flags
        count = (self.counter if counter is None else counter).to_bytes(4, "big")
        body = rp_hash + bytes([value]) + count
        if attested:
            cid = self.credential_id if credential_id is None else credential_id
            body += b"\x00" * 16 + len(cid).to_bytes(2, "big") + cid
            body += self.cose_key() if cose is None else cose
        return body + trailing

    # --- the two ceremonies, as the app sends them -------------------------------------

    def register(
        self,
        options: dict[str, Any],
        *,
        origin: str = ORIGIN,
        ceremony: str = "webauthn.create",
        challenge: str | None = None,
        fmt: str = "none",
        att_stmt: dict[str, Any] | None = None,
        raw_id: bytes | None = None,
        cross_origin: object = None,
        **auth_kwargs: Any,
    ) -> dict[str, Any]:
        public_key = options.get("publicKey", options)
        self.user_handle = unb64url(public_key["user"]["id"])
        client_data = self.client_data(
            ceremony,
            challenge if challenge is not None else public_key["challenge"],
            origin=origin,
            cross_origin=cross_origin,
        )
        attestation = cbor2.dumps(
            {
                "fmt": fmt,
                "attStmt": att_stmt if att_stmt is not None else {},
                "authData": self.auth_data(attested=True, **auth_kwargs),
            }
        )
        rid = self.credential_id if raw_id is None else raw_id
        return {
            "id": b64url(rid),
            "rawId": b64url(rid),
            "type": "public-key",
            "authenticatorAttachment": "platform",
            "clientExtensionResults": {},
            "response": {
                "clientDataJSON": b64url(client_data),
                "attestationObject": b64url(attestation),
                "transports": ["internal", "hybrid"],
            },
        }

    def assertion(
        self,
        options: dict[str, Any],
        *,
        origin: str = ORIGIN,
        ceremony: str = "webauthn.get",
        challenge: str | None = None,
        signing_key: ec.EllipticCurvePrivateKey | None = None,
        user_handle: bytes | None | str = "stored",
        tamper: bool = False,
        cross_origin: object = None,
        **auth_kwargs: Any,
    ) -> dict[str, Any]:
        public_key = options.get("publicKey", options)
        client_data = self.client_data(
            ceremony,
            challenge if challenge is not None else public_key["challenge"],
            origin=origin,
            cross_origin=cross_origin,
        )
        auth_data = self.auth_data(attested=False, **auth_kwargs)
        signer = signing_key if signing_key is not None else self.key
        signature = signer.sign(
            auth_data + hashlib.sha256(client_data).digest(), ec.ECDSA(hashes.SHA256())
        )
        if tamper:
            signature = signature[:-1] + bytes([signature[-1] ^ 0x01])
        response: dict[str, Any] = {
            "clientDataJSON": b64url(client_data),
            "authenticatorData": b64url(auth_data),
            "signature": b64url(signature),
        }
        handle = self.user_handle if user_handle == "stored" else user_handle
        if isinstance(handle, bytes):
            response["userHandle"] = b64url(handle)
        return {
            "id": b64url(self.credential_id),
            "rawId": b64url(self.credential_id),
            "type": "public-key",
            "authenticatorAttachment": "platform",
            "clientExtensionResults": {},
            "response": response,
        }
