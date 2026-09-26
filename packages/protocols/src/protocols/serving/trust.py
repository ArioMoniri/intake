"""INT-058 — the runtime half of a signed protocol bundle: verify, then load.

files/04 §7: *"the runtime refuses unsigned or hash-mismatched packs"*;
files/10 §8: *"unsigned or tampered packs fail to load at runtime"*. This
module is the only way to turn archive bytes into a :class:`VerifiedBundle`,
and :class:`~protocols.serving.pins.ServedBundles` serves nothing else.

**The order of checks is the security property.** Nothing inside the archive
is parsed — not the gzip stream, not a tar header, not a JSON byte — until the
signature over the raw bytes has verified. Then:

1. a signature exists at all (:class:`BundleUnsigned`);
2. it is the container ``cosign sign-blob --bundle`` writes — a sigstore
   bundle carrying a ``messageSignature`` over a blob, not a DSSE attestation
   (:class:`BundleSignatureInvalid`) and not a keyless certificate identity
   (:class:`BundleUntrustedSigner`);
3. the digest it declares is the archive's sha256, and so is any digest the
   caller expected (:class:`BundleHashMismatch`);
4. the ECDSA P-256 / SHA-256 signature verifies under the trust root
   (:class:`BundleSignatureInvalid` — a tampered archive, a corrupted
   signature and another key's signature are the same observation to ECDSA,
   and all three are refused the same way);
5. only now is the archive inflated, bounded, and read in memory — never
   extracted to disk — as flat regular files forming exactly the manifest's
   set (:class:`BundleArchiveMalformed`);
6. every member hashes to its manifest row, and ``resolved_protocol.json``
   re-derives the resolved-protocol hash the manifest states
   (:class:`BundleHashMismatch`).

Steps 5 and 6 refuse archives a trusted key *did* sign. They are there because
a signature proves who produced the bytes, not that the bytes are a bundle.

**The trust root** is an EC P-256 public key — the public half of the key
``make sign`` used — read from the file :data:`TRUST_ROOT_ENV` names. There is
no default and no development bypass: with nothing configured,
:func:`load_trust_root` raises :class:`TrustRootMissing` and nothing loads.
The production key's custody (KMS, OpenBao transit, or keyless CI identity)
is INT-019's decision, awaiting the owner; tests mint an ephemeral key.

**Deliberately not verified here.** No transparency-log inclusion proof: the
serving tier is offline and in-country, and a Rekor entry would add a public
network dependency to every session start. No keyless (Fulcio certificate)
bundle: trusting one needs an identity policy — which OIDC issuer, which
workflow subject — that nobody has decided, so it is refused rather than
accepted on a certificate chain alone.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import io
import json
import os
import tarfile
import zlib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import ClassVar, Final

from clinical_schemas.common import FrozenModel, Sha256
from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import Prehashed
from pydantic import ValidationError

from protocols.compile.archive import SIGNATURE_SUFFIX
from protocols.compile.bundle import MANIFEST, RESOLVED
from protocols.compile.resolve import ResolvedProtocol, protocol_hash_of

__all__ = [
    "MAX_ARCHIVE_BYTES",
    "MAX_UNPACKED_BYTES",
    "TRUST_ROOT_ENV",
    "BundleArchiveMalformed",
    "BundleHashMismatch",
    "BundleKey",
    "BundleManifest",
    "BundleRefused",
    "BundleSignatureInvalid",
    "BundleUnsigned",
    "BundleUntrustedSigner",
    "TrustRoot",
    "TrustRootInvalid",
    "TrustRootMissing",
    "VerifiedBundle",
    "load_trust_root",
    "load_verified_bundle",
    "verify_bundle",
]

TRUST_ROOT_ENV: Final = "INTAKE_PROTOCOL_TRUST_ROOT"
"""Path to the PEM public key protocol bundles must verify under. No default."""

MAX_ARCHIVE_BYTES: Final = 32 * 1024 * 1024
"""A compiled bundle is tens of kilobytes; anything near this is not one."""

MAX_UNPACKED_BYTES: Final = 64 * 1024 * 1024
"""Inflation bound, applied after the signature verified — defence in depth
against a trusted key signing a decompression bomb, not the primary control."""

_SIGSTORE_MEDIA_TYPE_PREFIX: Final = "application/vnd.dev.sigstore.bundle"
_SHA2_256: Final = "SHA2_256"
_GZIP_ONLY: Final = 16 + zlib.MAX_WBITS
_INT_019: Final = (
    "the production signing key's custody (KMS, OpenBao transit or keyless CI "
    "identity) is INT-019, awaiting the owner"
)


# --------------------------------------------------------------------------- refusals


class BundleRefused(Exception):
    """A protocol bundle the runtime will not load. Every subclass fails closed.

    ``reason`` is a stable, PHI-free id for a log line or the
    ``sec.pack_signature_failures`` counter (observability/metrics_catalog.yaml).
    """

    reason: ClassVar[str] = "refused"


class TrustRootMissing(BundleRefused):
    """No trust root is configured, so no bundle can be trusted (INT-019)."""

    reason = "trust_root_missing"


class TrustRootInvalid(BundleRefused):
    """The configured trust root is not an EC P-256 public key."""

    reason = "trust_root_invalid"


class BundleUnsigned(BundleRefused):
    """There is no signature to verify."""

    reason = "unsigned"


class BundleSignatureInvalid(BundleRefused):
    """The signature is malformed, or does not verify under the trust root."""

    reason = "signature_invalid"


class BundleUntrustedSigner(BundleRefused):
    """Signed by an identity this runtime has no policy to trust."""

    reason = "untrusted_signer"


class BundleHashMismatch(BundleRefused):
    """A digest the bundle or the caller states is not the digest of the bytes."""

    reason = "hash_mismatch"


class BundleArchiveMalformed(BundleRefused):
    """The bytes are not a compiled protocol bundle, signed or not."""

    reason = "archive_malformed"


# --------------------------------------------------------------------------- trust root


@dataclass(frozen=True, eq=False)
class TrustRoot:
    """The one public key protocol bundles must be signed by."""

    key_id: str
    public_key: ec.EllipticCurvePublicKey

    @classmethod
    def from_pem(cls, pem: bytes) -> TrustRoot:
        """Accept an EC P-256 public key (what ``cosign generate-key-pair``,
        OpenBao transit ``ecdsa-p256`` and a KMS ``ECC_NIST_P256`` key produce)
        and nothing else — no algorithm is negotiated from a signature."""
        try:
            loaded = serialization.load_pem_public_key(pem)
        except (ValueError, TypeError, UnsupportedAlgorithm) as exc:
            raise TrustRootInvalid(
                "the protocol-bundle trust root is not a PEM public key; a runtime "
                "holds only the public half, never a private key"
            ) from exc
        if not isinstance(loaded, ec.EllipticCurvePublicKey) or not isinstance(
            loaded.curve, ec.SECP256R1
        ):
            raise TrustRootInvalid("the protocol-bundle trust root must be an EC P-256 public key")
        der = loaded.public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        return cls(key_id=hashlib.sha256(der).hexdigest(), public_key=loaded)


def load_trust_root(env: Mapping[str, str] | None = None) -> TrustRoot:
    """The trust root :data:`TRUST_ROOT_ENV` names, or :class:`TrustRootMissing`."""
    source = os.environ if env is None else env
    configured = source.get(TRUST_ROOT_ENV, "").strip()
    if not configured:
        raise TrustRootMissing(
            f"no protocol-bundle trust root is configured ({TRUST_ROOT_ENV} is unset); "
            f"no bundle loads without one — {_INT_019}"
        )
    path = Path(configured)
    try:
        pem = path.read_bytes()
    except OSError as exc:
        raise TrustRootMissing(
            f"{TRUST_ROOT_ENV} names {path}, which cannot be read; no bundle loads — {_INT_019}"
        ) from exc
    return TrustRoot.from_pem(pem)


# --------------------------------------------------------------------------- the bundle


@dataclass(frozen=True)
class BundleKey:
    """What one compile is *for*: a pack, spoken in one locale, by one voice.

    The resolved-protocol hash is voice-independent, so two voices' bundles of
    one pack share it; the deployment slot is this triple (INT-297 keys the
    clip cache the same way)."""

    pack_id: str
    locale: str
    voice: str


class BundleManifest(FrozenModel):
    """``manifest.json`` as :func:`protocols.compile.compile_bundle` writes it."""

    pack_id: str
    version: str
    chain: tuple[str, ...]
    overlays: tuple[str, ...]
    voice: str
    locale: str
    resolved_protocol_hash: Sha256
    opt_template_id: str
    opt_sha256: Sha256
    artifacts: dict[str, Sha256]


_MINT: Final = object()


class VerifiedBundle:
    """A bundle whose signature, digest and content hashes all verified.

    Minted only by :func:`verify_bundle`: the constructor refuses any other
    caller, so "this protocol came out of a verified bundle" is a property of
    the type rather than a promise at each call site.
    """

    __slots__ = ("_archive_sha256", "_artifacts", "_manifest", "_protocol", "_signer_key_id")

    def __init__(
        self,
        *,
        token: object,
        manifest: BundleManifest,
        protocol: ResolvedProtocol,
        artifacts: Mapping[str, bytes],
        archive_sha256: str,
        signer_key_id: str,
    ) -> None:
        if token is not _MINT:
            raise TypeError("a VerifiedBundle is minted only by verify_bundle")
        self._manifest = manifest
        self._protocol = protocol
        self._artifacts: Mapping[str, bytes] = MappingProxyType(dict(artifacts))
        self._archive_sha256 = archive_sha256
        self._signer_key_id = signer_key_id

    @property
    def manifest(self) -> BundleManifest:
        return self._manifest

    @property
    def protocol(self) -> ResolvedProtocol:
        """The resolved document the composition root runs a session on."""
        return self._protocol

    @property
    def artifacts(self) -> Mapping[str, bytes]:
        """Every archive member, read-only."""
        return self._artifacts

    @property
    def archive_sha256(self) -> str:
        return self._archive_sha256

    @property
    def signer_key_id(self) -> str:
        return self._signer_key_id

    @property
    def pack_id(self) -> str:
        return self._manifest.pack_id

    @property
    def version(self) -> str:
        return self._manifest.version

    @property
    def locale(self) -> str:
        return self._manifest.locale

    @property
    def voice(self) -> str:
        return self._manifest.voice

    @property
    def resolved_protocol_hash(self) -> str:
        """Re-derived from the verified document, never merely read."""
        return self._protocol.resolved_protocol_hash

    @property
    def key(self) -> BundleKey:
        return BundleKey(pack_id=self.pack_id, locale=self.locale, voice=self.voice)

    def __repr__(self) -> str:
        return (
            f"VerifiedBundle(pack_id={self.pack_id!r}, version={self.version!r}, "
            f"resolved_protocol_hash={self.resolved_protocol_hash!r}, "
            f"archive_sha256={self.archive_sha256!r})"
        )


# --------------------------------------------------------------------------- verification


@dataclass(frozen=True)
class _MessageSignature:
    signature: bytes
    digest: bytes | None


def _decode_b64(value: object, what: str) -> bytes:
    if not isinstance(value, str) or not value:
        raise BundleSignatureInvalid(f"the signature bundle's {what} is not a base64 string")
    try:
        return base64.b64decode(value, validate=True)
    except binascii.Error as exc:
        raise BundleSignatureInvalid(f"the signature bundle's {what} is not base64") from exc


def _parse_signature(raw: bytes) -> _MessageSignature:
    """The ``messageSignature`` of a sigstore bundle, or a typed refusal."""
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BundleSignatureInvalid("the signature file is not a sigstore bundle") from exc
    media_type = payload.get("mediaType") if isinstance(payload, dict) else None
    if not isinstance(media_type, str) or not media_type.startswith(_SIGSTORE_MEDIA_TYPE_PREFIX):
        raise BundleSignatureInvalid(
            "the signature file is not a sigstore bundle (the container `cosign sign-blob "
            "--bundle` writes)"
        )
    material = payload.get("verificationMaterial")
    if isinstance(material, dict) and (
        "certificate" in material or "x509CertificateChain" in material
    ):
        raise BundleUntrustedSigner(
            "the bundle is signed by a keyless certificate identity; this runtime trusts "
            f"only its configured public key and has no identity policy — {_INT_019}"
        )
    message = payload.get("messageSignature")
    if not isinstance(message, dict):
        raise BundleSignatureInvalid(
            "the sigstore bundle carries no messageSignature; an attestation envelope "
            "is not a signature over the archive"
        )
    signature = _decode_b64(message.get("signature"), "signature")
    declared = message.get("messageDigest")
    if declared is None:
        return _MessageSignature(signature=signature, digest=None)
    if not isinstance(declared, dict) or declared.get("algorithm") != _SHA2_256:
        raise BundleSignatureInvalid("the signed digest is not SHA2_256")
    return _MessageSignature(
        signature=signature, digest=_decode_b64(declared.get("digest"), "messageDigest")
    )


def _is_flat_name(name: str) -> bool:
    return bool(name) and name not in {".", ".."} and not any(c in name for c in "/\\\x00")


def _read_members(archive: bytes) -> dict[str, bytes]:
    """Inflate within :data:`MAX_UNPACKED_BYTES` and read every member in memory."""
    inflater = zlib.decompressobj(wbits=_GZIP_ONLY)
    try:
        raw = inflater.decompress(archive, MAX_UNPACKED_BYTES)
    except zlib.error as exc:
        raise BundleArchiveMalformed("the archive is not a gzip stream") from exc
    if inflater.unconsumed_tail:
        raise BundleArchiveMalformed(f"the archive inflates past {MAX_UNPACKED_BYTES} bytes")
    if not inflater.eof:
        raise BundleArchiveMalformed("the archive's gzip stream is truncated")
    if inflater.unused_data:
        raise BundleArchiveMalformed("the archive carries trailing bytes after its gzip stream")
    members: dict[str, bytes] = {}
    try:
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as tar:
            for info in tar.getmembers():
                if not _is_flat_name(info.name) or not info.isreg():
                    raise BundleArchiveMalformed(
                        f"archive member {info.name!r} is not a flat regular file"
                    )
                if info.name in members:
                    raise BundleArchiveMalformed(f"archive member {info.name!r} appears twice")
                # A regular USTAR member's bytes sit contiguously at offset_data
                # in the stream already in memory: nothing is extracted anywhere.
                members[info.name] = raw[info.offset_data : info.offset_data + info.size]
    except tarfile.TarError as exc:
        raise BundleArchiveMalformed("the archive is not a tar stream") from exc
    return members


def _check_contents(
    members: Mapping[str, bytes],
) -> tuple[BundleManifest, ResolvedProtocol]:
    raw_manifest = members.get(MANIFEST)
    if raw_manifest is None:
        raise BundleArchiveMalformed(f"the archive carries no {MANIFEST}")
    try:
        manifest = BundleManifest.model_validate_json(raw_manifest)
    except ValidationError as exc:
        raise BundleArchiveMalformed(f"{MANIFEST} is not a compiled manifest") from exc
    listed = {*manifest.artifacts, MANIFEST}
    if listed != set(members):
        raise BundleArchiveMalformed(
            f"archive members and {MANIFEST} disagree on {sorted(listed ^ set(members))}"
        )
    for name, expected in sorted(manifest.artifacts.items()):
        if not hmac.compare_digest(hashlib.sha256(members[name]).hexdigest(), expected):
            raise BundleHashMismatch(f"{name} does not hash to its {MANIFEST} row")
    if RESOLVED not in manifest.artifacts:
        raise BundleArchiveMalformed(f"the archive carries no {RESOLVED}")
    try:
        protocol = ResolvedProtocol.model_validate_json(members[RESOLVED])
    except ValidationError as exc:
        raise BundleArchiveMalformed(f"{RESOLVED} is not a resolved protocol") from exc
    derived = protocol_hash_of(protocol)
    if not (derived == protocol.resolved_protocol_hash == manifest.resolved_protocol_hash):
        raise BundleHashMismatch(
            f"the resolved protocol re-derives to {derived}, not to the hash it states"
        )
    stated = (manifest.pack_id, manifest.version, manifest.locale)
    if stated != (protocol.pack_id, protocol.version, protocol.locale):
        raise BundleArchiveMalformed(
            f"{MANIFEST} names {stated}, its document "
            f"{(protocol.pack_id, protocol.version, protocol.locale)}"
        )
    return manifest, protocol


def verify_bundle(
    archive: bytes,
    signature: bytes | None,
    trust_root: TrustRoot,
    *,
    expected_sha256: str | None = None,
) -> VerifiedBundle:
    """Verify ``signature`` over ``archive`` under ``trust_root``, then read it.

    ``expected_sha256`` is the digest a deploy record pins, when there is one.
    Raises a :class:`BundleRefused` subclass for every way the bytes fall short.
    """
    if signature is None or not signature.strip():
        raise BundleUnsigned("the protocol bundle carries no signature; it is not loaded")
    if len(archive) > MAX_ARCHIVE_BYTES:
        raise BundleArchiveMalformed(f"the archive is larger than {MAX_ARCHIVE_BYTES} bytes")
    digest = hashlib.sha256(archive).digest()
    if expected_sha256 is not None and not hmac.compare_digest(
        expected_sha256.strip().lower().encode("utf-8"), digest.hex().encode("ascii")
    ):
        raise BundleHashMismatch("the archive is not the one the deploy record pins")
    message = _parse_signature(signature)
    if message.digest is not None and not hmac.compare_digest(message.digest, digest):
        raise BundleHashMismatch("the archive is not the blob the signature declares")
    try:
        trust_root.public_key.verify(
            message.signature, digest, ec.ECDSA(Prehashed(hashes.SHA256()))
        )
    except InvalidSignature as exc:
        raise BundleSignatureInvalid(
            f"the signature does not verify under trust-root key {trust_root.key_id}: the "
            "archive or the signature was altered, or another key signed it"
        ) from exc
    members = _read_members(archive)
    manifest, protocol = _check_contents(members)
    return VerifiedBundle(
        token=_MINT,
        manifest=manifest,
        protocol=protocol,
        artifacts=members,
        archive_sha256=digest.hex(),
        signer_key_id=trust_root.key_id,
    )


def load_verified_bundle(
    archive_path: Path,
    trust_root: TrustRoot,
    *,
    expected_sha256: str | None = None,
) -> VerifiedBundle:
    """Read ``bundle.tar.gz`` and the ``.sigstore.json`` beside it, once, then
    :func:`verify_bundle` the bytes that were read (no check-then-reread)."""
    if archive_path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise BundleArchiveMalformed(f"{archive_path} is larger than {MAX_ARCHIVE_BYTES} bytes")
    signature_path = archive_path.with_name(archive_path.name + SIGNATURE_SUFFIX)
    signature = signature_path.read_bytes() if signature_path.is_file() else None
    return verify_bundle(
        archive_path.read_bytes(), signature, trust_root, expected_sha256=expected_sha256
    )
