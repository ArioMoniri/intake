"""A synthetic App Attest world for tests (INT-344) — test root, device, objects.

Apple's real chain cannot sign anything for us, so every accept/refuse branch of
the verifier is driven by a PKI built here at run time: a test root, an
intermediate and a per-device leaf that carries the nonce extension exactly the
way Apple's does (OID 1.2.840.113635.100.8.2, a SEQUENCE holding one [1]-tagged
OCTET STRING — the shape of the credCert in Apple's own published example). The
test root is only ever handed to a verifier through its ``root=`` argument; the
production default is the pinned Apple root, and a test asserts that.

No key material is committed: every key is generated when the module runs.
Uniquely named (like api_harness.py) so tests import it directly.
"""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import cbor2
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

TEAM_ID = "ABCDE12345"
BUNDLE_ID = "com.ariomoniri.intakemobile"
NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)

NONCE_OID = x509.ObjectIdentifier("1.2.840.113635.100.8.2")
AAGUID_PRODUCTION = b"appattest" + b"\x00" * 7
AAGUID_DEVELOPMENT = b"appattestdevelop"
FLAG_ATTESTED_CREDENTIAL_DATA = 0x40


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def _name(common_name: str) -> x509.Name:
    return x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "INTAKE synthetic test PKI"),
        ]
    )


@dataclass(frozen=True)
class Authority:
    key: ec.EllipticCurvePrivateKey
    cert: x509.Certificate

    @property
    def der(self) -> bytes:
        return self.cert.public_bytes(serialization.Encoding.DER)


def authority(
    common_name: str,
    issuer: Authority | None = None,
    *,
    not_before: datetime = NOW - timedelta(days=30),
    not_after: datetime = NOW + timedelta(days=365),
    ca: bool | None = True,
) -> Authority:
    """A CA certificate: self-signed when ``issuer`` is None. ``ca=False``
    builds the wrong thing on purpose — a signer that is not a CA — and
    ``ca=None`` one that says nothing about it (no BasicConstraints)."""
    key = ec.generate_private_key(ec.SECP384R1())
    subject = _name(common_name)
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer.cert.subject if issuer is not None else subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
    )
    if ca is not None:
        builder = builder.add_extension(
            x509.BasicConstraints(ca=ca, path_length=None), critical=True
        )
    signer = issuer.key if issuer is not None else key
    return Authority(key=key, cert=builder.sign(signer, hashes.SHA384()))


def der(tag: int, contents: bytes) -> bytes:
    """One DER TLV with a minimal definite length (short or long form)."""
    size = len(contents)
    if size < 0x80:
        return bytes([tag, size]) + contents
    encoded = size.to_bytes((size.bit_length() + 7) // 8, "big")
    return bytes([tag, 0x80 | len(encoded)]) + encoded + contents


def nonce_extension_value(nonce: bytes) -> bytes:
    """DER SEQUENCE { [1] EXPLICIT OCTET STRING nonce } — Apple's credCert shape."""
    return der(0x30, der(0xA1, der(0x04, nonce)))


@dataclass
class Pki:
    root: Authority
    intermediate: Authority

    @classmethod
    def build(cls) -> Pki:
        root = authority("Synthetic App Attestation Root CA")
        return cls(root=root, intermediate=authority("Synthetic App Attestation CA 1", root))


def cose_key(point: bytes) -> dict[int, Any]:
    """COSE_Key for a P-256 public key (RFC 8152: kty EC2, alg ES256, crv P-256)."""
    return {1: 2, 3: -7, -1: 1, -2: point[1:33], -3: point[33:65]}


@dataclass
class Device:
    """One app install on one device: an App Attest key pair and its identity."""

    pki: Pki
    team_id: str = TEAM_ID
    bundle_id: str = BUNDLE_ID
    key: ec.EllipticCurvePrivateKey = field(
        default_factory=lambda: ec.generate_private_key(ec.SECP256R1())
    )

    @property
    def point(self) -> bytes:
        return self.key.public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )

    @property
    def key_id_raw(self) -> bytes:
        return sha256(self.point)

    @property
    def key_id(self) -> str:
        """What DCAppAttestService.generateKey returns: base64(SHA256(point))."""
        return b64(self.key_id_raw)

    @property
    def rp_id_hash(self) -> bytes:
        return sha256(f"{self.team_id}.{self.bundle_id}".encode())

    def leaf(
        self,
        nonce: bytes,
        *,
        issuer: Authority | None = None,
        not_after: datetime = NOW + timedelta(days=3),
        ca: bool = False,
        nonce_extension: bytes | None = None,
    ) -> bytes:
        """``nonce_extension`` replaces the extension's DER value verbatim;
        ``b""`` leaves the extension out altogether."""
        signer = issuer if issuer is not None else self.pki.intermediate
        builder = (
            x509.CertificateBuilder()
            .subject_name(_name(self.key_id_raw.hex()))
            .issuer_name(signer.cert.subject)
            .public_key(self.key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(NOW - timedelta(days=1))
            .not_valid_after(not_after)
            .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True)
        )
        value = nonce_extension if nonce_extension is not None else nonce_extension_value(nonce)
        if value:
            builder = builder.add_extension(
                x509.UnrecognizedExtension(NONCE_OID, value), critical=False
            )
        cert = builder.sign(signer.key, hashes.SHA256())
        return cert.public_bytes(serialization.Encoding.DER)

    def auth_data(
        self,
        *,
        counter: int = 0,
        aaguid: bytes = AAGUID_PRODUCTION,
        rp_id_hash: bytes | None = None,
        credential_id: bytes | None = None,
        extensions: dict[str, Any] | None = None,
        cose_point: bytes | None = None,
        trailing: bytes = b"",
    ) -> bytes:
        credential = credential_id if credential_id is not None else self.key_id_raw
        data = (
            (rp_id_hash if rp_id_hash is not None else self.rp_id_hash)
            + bytes([FLAG_ATTESTED_CREDENTIAL_DATA])
            + counter.to_bytes(4, "big")
            + aaguid
            + len(credential).to_bytes(2, "big")
            + credential
            + cbor2.dumps(cose_key(cose_point if cose_point is not None else self.point))
        )
        if extensions is not None:
            data += cbor2.dumps(extensions)
        return data + trailing

    def attestation_object(
        self,
        client_data: str,
        *,
        counter: int = 0,
        aaguid: bytes = AAGUID_PRODUCTION,
        rp_id_hash: bytes | None = None,
        credential_id: bytes | None = None,
        extensions: dict[str, Any] | None = None,
        cose_point: bytes | None = None,
        trailing: bytes = b"",
        nonce_client_data: str | None = None,
        chain: list[bytes] | None = None,
        issuer: Authority | None = None,
        leaf_not_after: datetime = NOW + timedelta(days=3),
        leaf_ca: bool = False,
        nonce_extension: bytes | None = None,
        raw_auth_data: bytes | None = None,
        fmt: str = "apple-appattest",
    ) -> bytes:
        """Raw CBOR, signed over ``client_data`` unless ``nonce_client_data``
        substitutes another value for the nonce the leaf commits to.
        ``raw_auth_data`` replaces the authenticator data verbatim (the nonce
        still commits to it, so only its parse can refuse it)."""
        auth_data = (
            raw_auth_data
            if raw_auth_data is not None
            else self.auth_data(
                counter=counter,
                aaguid=aaguid,
                rp_id_hash=rp_id_hash,
                credential_id=credential_id,
                extensions=extensions,
                cose_point=cose_point,
                trailing=trailing,
            )
        )
        signed_over = nonce_client_data if nonce_client_data is not None else client_data
        nonce = sha256(auth_data + sha256(signed_over.encode()))
        x5c = (
            chain
            if chain is not None
            else [
                self.leaf(
                    nonce,
                    issuer=issuer,
                    not_after=leaf_not_after,
                    ca=leaf_ca,
                    nonce_extension=nonce_extension,
                ),
                (issuer if issuer is not None else self.pki.intermediate).der,
            ]
        )
        return cbor2.dumps(
            {
                "fmt": fmt,
                "attStmt": {"x5c": x5c, "receipt": b"synthetic-receipt"},
                "authData": auth_data,
            }
        )

    def attest(self, client_data: str, **knobs: Any) -> str:
        """Base64, as @expo/app-integrity's attestKeyAsync returns it."""
        return b64(self.attestation_object(client_data, **knobs))

    def assertion_object(
        self,
        client_data: str,
        counter: int,
        *,
        rp_id_hash: bytes | None = None,
        signer: ec.EllipticCurvePrivateKey | None = None,
    ) -> bytes:
        authenticator_data = (
            (rp_id_hash if rp_id_hash is not None else self.rp_id_hash)
            + bytes([FLAG_ATTESTED_CREDENTIAL_DATA])
            + counter.to_bytes(4, "big")
        )
        nonce = sha256(authenticator_data + sha256(client_data.encode()))
        signature = (signer if signer is not None else self.key).sign(
            nonce, ec.ECDSA(hashes.SHA256())
        )
        return cbor2.dumps({"signature": signature, "authenticatorData": authenticator_data})

    def assertion(self, client_data: str, counter: int, **knobs: Any) -> str:
        """Base64, as @expo/app-integrity's generateAssertionAsync returns it."""
        return b64(self.assertion_object(client_data, counter, **knobs))
