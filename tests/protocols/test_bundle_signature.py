"""INT-058 acceptance: signed protocol bundles.

The acceptance names this file: *"compiler emits bundle.tar.gz signed; runtime
refuses unsigned/tampered; note meta shows protocol hash"*. files/04 §7 is the
longer form: *"the compiler emits a bundle (YAML + compiled outputs + clip
manifest) signed with cosign; the runtime refuses unsigned or hash-mismatched
packs; the resolved-protocol hash is pinned per session and shown in the note
meta."* files/10 §9 row `protocol-registry` asks for "load-time signature tests".

**The key.** Every signing key here is an EC P-256 key generated in memory for
one test and never written anywhere: no private key is committed and no
production key exists (its custody is INT-019, awaiting the owner). What the
tests produce is exactly what ``cosign sign-blob --key <ref> --bundle`` writes
— a sigstore bundle carrying a ``messageSignature`` whose signature is an
ASN.1 DER ECDSA-P256-SHA256 signature over the archive bytes — so the verifier
under test is the one a cosign-signed bundle meets in production.

Everything compiled here is the synthetic fixture pack tree (files/04 §7).
"""

from __future__ import annotations

import base64
import datetime
import gzip
import hashlib
import io
import json
import tarfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from clinical_schemas.note import NoteMeta, ScreeningBlock, ScreeningProvenance
from clinical_schemas.session import SessionBudget, SessionState
from clinical_schemas.triage import RulesTriageResult, TriageLevel
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from intake_platform.legal import LegalStringsCatalog
from intake_voice_runtime.note import (
    NOTE_COPY_KEYS,
    compose,
    note_copy_from_legal_strings,
    render_soap,
)
from protocols.bindings import OperationalTemplate
from protocols.cli import main
from protocols.compile import CompiledBundle, LifeThreatSet, compile_bundle, write_bundle
from protocols.compile.archive import (
    BUNDLE_ARCHIVE,
    DIGEST_SUFFIX,
    SIGNATURE_SUFFIX,
    archive_sha256,
    bundle_archive,
)
from protocols.compile.bundle import MANIFEST, RESOLVED
from protocols.compile.resolve import protocol_hash_of
from protocols.loader import PackRegistry
from protocols.serving import trust
from protocols.serving.pins import (
    BundleKey,
    PinConflict,
    PublishedVersionConflict,
    ServedBundles,
    SessionNotPinned,
    UnknownBundle,
)
from protocols.serving.trust import (
    TRUST_ROOT_ENV,
    BundleArchiveMalformed,
    BundleHashMismatch,
    BundleRefused,
    BundleSignatureInvalid,
    BundleUnsigned,
    BundleUntrustedSigner,
    TrustRoot,
    TrustRootInvalid,
    TrustRootMissing,
    VerifiedBundle,
    load_trust_root,
    load_verified_bundle,
    verify_bundle,
)

PACK_ID = "base.derlenebilir"
VOICE = "sentetik-ses"
LOCALE = "tr"
OVERLAY = "overlay.sentetik_bir"
SIGSTORE_MEDIA_TYPE = "application/vnd.dev.sigstore.bundle.v0.3+json"
REPO = Path(__file__).resolve().parents[2]
SYNTHETIC_STRINGS = REPO / "tests" / "fixtures" / "legal" / "strings.synthetic.yaml"
KEY = BundleKey(pack_id=PACK_ID, locale=LOCALE, voice=VOICE)


# ------------------------------------------------------------------ helpers


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _new_key() -> ec.EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP256R1())


def _public_pem(key: ec.EllipticCurvePrivateKey | rsa.RSAPrivateKey) -> bytes:
    return key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )


def _cosign_bundle(
    archive: bytes,
    key: ec.EllipticCurvePrivateKey,
    *,
    with_digest: bool = True,
    material: dict[str, Any] | None = None,
) -> bytes:
    """What ``cosign sign-blob --key <ref> --bundle out.sigstore.json`` writes."""
    signature = key.sign(archive, ec.ECDSA(hashes.SHA256()))
    message: dict[str, Any] = {"signature": _b64(signature)}
    if with_digest:
        message["messageDigest"] = {
            "algorithm": "SHA2_256",
            "digest": _b64(hashlib.sha256(archive).digest()),
        }
    return json.dumps(
        {
            "mediaType": SIGSTORE_MEDIA_TYPE,
            "verificationMaterial": material
            if material is not None
            else {"publicKey": {"hint": "sentetik-anahtar"}},
            "messageSignature": message,
        }
    ).encode("utf-8")


def _tar_gz(members: list[tuple[str, bytes]], *, extra: tuple[tarfile.TarInfo, ...] = ()) -> bytes:
    """A hand-built archive, for the shapes the compiler never emits."""
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        for name, data in members:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        for info in extra:
            tar.addfile(info)
    return gzip.compress(raw.getvalue(), mtime=0)


def _members(archive: bytes) -> dict[str, bytes]:
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        return {
            info.name: tar.extractfile(info).read()  # type: ignore[union-attr]
            for info in tar.getmembers()
        }


def _rehash_manifest(members: dict[str, bytes]) -> dict[str, bytes]:
    """Recompute every manifest row, as a signer re-signing an edit would."""
    manifest = json.loads(members[MANIFEST])
    manifest["artifacts"] = {
        name: hashlib.sha256(data).hexdigest()
        for name, data in sorted(members.items())
        if name != MANIFEST
    }
    return {**members, MANIFEST: json.dumps(manifest, sort_keys=True).encode("utf-8")}


def _compile(
    registry: PackRegistry,
    life_threat: LifeThreatSet,
    template: OperationalTemplate,
    overlays: tuple[str, ...] = (),
) -> CompiledBundle:
    return compile_bundle(
        pack_id=PACK_ID,
        registry=registry,
        life_threat=life_threat,
        template=template,
        voice=VOICE,
        overlays=overlays,
    )


# ------------------------------------------------------------------ fixtures


@pytest.fixture
def bundle(
    registry: PackRegistry, life_threat: LifeThreatSet, template: OperationalTemplate
) -> CompiledBundle:
    return _compile(registry, life_threat, template)


@pytest.fixture
def tightened(
    registry: PackRegistry, life_threat: LifeThreatSet, template: OperationalTemplate
) -> CompiledBundle:
    """The same pack with an overlay applied: a second, different resolved hash."""
    return _compile(registry, life_threat, template, (OVERLAY,))


@pytest.fixture
def signing_key() -> ec.EllipticCurvePrivateKey:
    return _new_key()


@pytest.fixture
def trust_root(signing_key: ec.EllipticCurvePrivateKey) -> TrustRoot:
    return TrustRoot.from_pem(_public_pem(signing_key))


@pytest.fixture
def archive(bundle: CompiledBundle) -> bytes:
    return bundle_archive(bundle)


@pytest.fixture
def sign(signing_key: ec.EllipticCurvePrivateKey) -> Callable[[bytes], bytes]:
    def _sign(blob: bytes) -> bytes:
        return _cosign_bundle(blob, signing_key)

    return _sign


# =================================================================== 1. the compiler emits it


class TestCompilerEmitsTheArchive:
    def test_write_bundle_emits_the_archive_and_its_digest(
        self, tmp_path: Path, bundle: CompiledBundle
    ) -> None:
        written = {path.name: path for path in write_bundle(bundle, tmp_path)}
        archive = written[BUNDLE_ARCHIVE].read_bytes()
        assert archive == bundle_archive(bundle)
        sidecar = written[BUNDLE_ARCHIVE + DIGEST_SUFFIX].read_text(encoding="ascii")
        # sha256sum's own format, so `shasum -a 256 -c` checks it by hand
        assert sidecar == f"{archive_sha256(archive)}  {BUNDLE_ARCHIVE}\n"
        assert archive_sha256(archive) == hashlib.sha256(archive).hexdigest()

    def test_the_archive_is_byte_identical_on_a_second_compile(
        self,
        registry: PackRegistry,
        life_threat: LifeThreatSet,
        template: OperationalTemplate,
        bundle: CompiledBundle,
    ) -> None:
        again = _compile(registry, life_threat, template)
        assert bundle_archive(again) == bundle_archive(bundle)

    def test_members_are_every_artifact_with_no_build_machine_metadata(
        self, bundle: CompiledBundle, archive: bytes
    ) -> None:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
            infos = tar.getmembers()
        assert [info.name for info in infos] == sorted(bundle.artifacts)
        for info in infos:
            assert info.isreg()
            assert (info.mtime, info.uid, info.gid, info.uname, info.gname) == (0, 0, 0, "", "")
            assert info.mode == 0o644
        assert _members(archive) == {
            name: content.encode("utf-8") for name, content in bundle.artifacts.items()
        }
        # the gzip header carries no timestamp either
        assert archive[4:8] == b"\x00\x00\x00\x00"

    def test_the_archive_carries_the_resolved_document_its_hash_is_derived_from(
        self, bundle: CompiledBundle, archive: bytes
    ) -> None:
        members = _members(archive)
        manifest = json.loads(members[MANIFEST])
        assert RESOLVED in manifest["artifacts"]
        assert manifest["artifacts"][RESOLVED] == hashlib.sha256(members[RESOLVED]).hexdigest()
        from protocols.compile.resolve import ResolvedProtocol

        document = ResolvedProtocol.model_validate_json(members[RESOLVED])
        assert protocol_hash_of(document) == bundle.resolved_protocol_hash
        assert document.resolved_protocol_hash == bundle.resolved_protocol_hash

    def test_the_cli_prints_the_archive_digest(
        self, tmp_path: Path, pack_tree: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        fixtures = pack_tree.parent
        exit_code = main(
            [
                "compile",
                "--pack",
                PACK_ID,
                "--packs",
                str(pack_tree),
                "--life-threat",
                str(fixtures / "life_threat_signed.yaml"),
                "--voice",
                VOICE,
                "--out",
                str(tmp_path),
            ]
        )
        assert exit_code == 0
        archive = (tmp_path / PACK_ID / BUNDLE_ARCHIVE).read_bytes()
        assert f"bundle_sha256: {archive_sha256(archive)}" in capsys.readouterr().out


# =================================================================== 2. the runtime verifies


class TestTheRuntimeLoadsOnlyWhatVerifies:
    def test_a_signed_bundle_verifies_and_carries_its_protocol(
        self,
        bundle: CompiledBundle,
        archive: bytes,
        sign: Callable[[bytes], bytes],
        trust_root: TrustRoot,
    ) -> None:
        verified = verify_bundle(archive, sign(archive), trust_root)
        assert verified.pack_id == PACK_ID
        assert verified.version == bundle.version
        assert (verified.locale, verified.voice) == (LOCALE, VOICE)
        assert verified.key == KEY
        assert verified.resolved_protocol_hash == bundle.resolved_protocol_hash
        assert verified.protocol.resolved_protocol_hash == bundle.resolved_protocol_hash
        assert verified.archive_sha256 == archive_sha256(archive)
        assert verified.signer_key_id == trust_root.key_id
        assert verified.artifacts == {
            name: content.encode("utf-8") for name, content in bundle.artifacts.items()
        }
        assert PACK_ID in repr(verified)

    def test_a_digestless_signature_still_verifies(
        self, archive: bytes, signing_key: ec.EllipticCurvePrivateKey, trust_root: TrustRoot
    ) -> None:
        signature = _cosign_bundle(archive, signing_key, with_digest=False)
        assert verify_bundle(archive, signature, trust_root).archive_sha256

    def test_load_from_dist_reads_the_signature_beside_the_archive(
        self,
        tmp_path: Path,
        bundle: CompiledBundle,
        sign: Callable[[bytes], bytes],
        trust_root: TrustRoot,
    ) -> None:
        write_bundle(bundle, tmp_path)
        path = tmp_path / PACK_ID / BUNDLE_ARCHIVE
        path.with_name(BUNDLE_ARCHIVE + SIGNATURE_SUFFIX).write_bytes(sign(path.read_bytes()))
        verified = load_verified_bundle(
            path, trust_root, expected_sha256=archive_sha256(path.read_bytes())
        )
        assert verified.resolved_protocol_hash == bundle.resolved_protocol_hash

    # ------------------------------------------------------------ unsigned

    @pytest.mark.parametrize("signature", [None, b"", b"  \n"])
    def test_an_unsigned_bundle_is_refused(
        self, archive: bytes, trust_root: TrustRoot, signature: bytes | None
    ) -> None:
        with pytest.raises(BundleUnsigned):
            verify_bundle(archive, signature, trust_root)

    def test_an_archive_with_no_signature_file_is_refused_at_load(
        self, tmp_path: Path, bundle: CompiledBundle, trust_root: TrustRoot
    ) -> None:
        write_bundle(bundle, tmp_path)
        with pytest.raises(BundleUnsigned):
            load_verified_bundle(tmp_path / PACK_ID / BUNDLE_ARCHIVE, trust_root)

    # ------------------------------------------------------------ tampered

    def test_a_tampered_archive_trips_the_signed_digest(
        self, archive: bytes, sign: Callable[[bytes], bytes], trust_root: TrustRoot
    ) -> None:
        signature = sign(archive)
        tampered = bytearray(archive)
        tampered[len(tampered) // 2] ^= 0x01
        with pytest.raises(BundleHashMismatch):
            verify_bundle(bytes(tampered), signature, trust_root)

    def test_a_tampered_archive_fails_the_signature_when_no_digest_is_declared(
        self, archive: bytes, signing_key: ec.EllipticCurvePrivateKey, trust_root: TrustRoot
    ) -> None:
        signature = _cosign_bundle(archive, signing_key, with_digest=False)
        members = _members(archive)
        members["slots.ts"] = members["slots.ts"] + b"// kurcalandi\n"
        tampered = _tar_gz(sorted(members.items()))
        with pytest.raises(BundleSignatureInvalid):
            verify_bundle(tampered, signature, trust_root)

    @pytest.mark.parametrize(
        "forged_signature",
        [b"\x30\x06\x02\x01\x01\x02\x01\x01", b"kesinlikle DER degil"],
        ids=["well-formed-der", "not-der"],
    )
    def test_a_forged_signature_is_refused(
        self,
        archive: bytes,
        sign: Callable[[bytes], bytes],
        trust_root: TrustRoot,
        forged_signature: bytes,
    ) -> None:
        forged = json.loads(sign(archive))
        forged["messageSignature"]["signature"] = _b64(forged_signature)
        with pytest.raises(BundleSignatureInvalid):
            verify_bundle(archive, json.dumps(forged).encode(), trust_root)

    def test_a_bundle_signed_by_another_key_is_refused(
        self, archive: bytes, trust_root: TrustRoot
    ) -> None:
        with pytest.raises(BundleSignatureInvalid, match=trust_root.key_id):
            verify_bundle(archive, _cosign_bundle(archive, _new_key()), trust_root)

    def test_an_unexpected_digest_is_refused_even_when_signed(
        self, archive: bytes, sign: Callable[[bytes], bytes], trust_root: TrustRoot
    ) -> None:
        with pytest.raises(BundleHashMismatch):
            verify_bundle(archive, sign(archive), trust_root, expected_sha256="0" * 64)

    @pytest.mark.parametrize(
        "material",
        [
            {"certificate": {"rawBytes": _b64(b"sentetik sertifika")}},
            {"x509CertificateChain": {"certificates": [{"rawBytes": _b64(b"sentetik")}]}},
        ],
        ids=["certificate", "chain"],
    )
    def test_a_keyless_certificate_identity_is_not_trusted(
        self,
        archive: bytes,
        signing_key: ec.EllipticCurvePrivateKey,
        trust_root: TrustRoot,
        material: dict[str, Any],
    ) -> None:
        signature = _cosign_bundle(archive, signing_key, material=material)
        with pytest.raises(BundleUntrustedSigner, match="INT-019"):
            verify_bundle(archive, signature, trust_root)

    @pytest.mark.parametrize(
        "mutate",
        [
            lambda doc: b"not json at all",
            lambda doc: b"\xff\xfe",
            lambda doc: json.dumps([doc]).encode(),
            lambda doc: json.dumps({**doc, "mediaType": "application/json"}).encode(),
            lambda doc: json.dumps({k: v for k, v in doc.items() if k != "mediaType"}).encode(),
            lambda doc: json.dumps(
                {
                    **{k: v for k, v in doc.items() if k != "messageSignature"},
                    "dsseEnvelope": {"payload": "", "signatures": []},
                }
            ).encode(),
            lambda doc: json.dumps(
                {**doc, "messageSignature": {**doc["messageSignature"], "signature": 7}}
            ).encode(),
            lambda doc: json.dumps(
                {**doc, "messageSignature": {**doc["messageSignature"], "signature": "@@@"}}
            ).encode(),
            lambda doc: json.dumps(
                {
                    **doc,
                    "messageSignature": {
                        **doc["messageSignature"],
                        "messageDigest": {"algorithm": "SHA2_512", "digest": _b64(b"x" * 64)},
                    },
                }
            ).encode(),
            lambda doc: json.dumps(
                {**doc, "messageSignature": {**doc["messageSignature"], "messageDigest": "sha"}}
            ).encode(),
        ],
        ids=[
            "not-json",
            "not-utf8",
            "not-an-object",
            "wrong-media-type",
            "no-media-type",
            "dsse-attestation",
            "signature-not-a-string",
            "signature-not-base64",
            "digest-not-sha256",
            "digest-not-an-object",
        ],
    )
    def test_a_malformed_signature_container_is_refused(
        self,
        archive: bytes,
        sign: Callable[[bytes], bytes],
        trust_root: TrustRoot,
        mutate: Callable[[dict[str, Any]], bytes],
    ) -> None:
        with pytest.raises(BundleSignatureInvalid):
            verify_bundle(archive, mutate(json.loads(sign(archive))), trust_root)

    # ------------------------------------------------ signed, but not a bundle we serve

    def test_a_member_that_disagrees_with_its_manifest_row_is_refused(
        self, archive: bytes, sign: Callable[[bytes], bytes], trust_root: TrustRoot
    ) -> None:
        members = _members(archive)
        members["slots.ts"] = members["slots.ts"] + b"// imzali ama tutarsiz\n"
        crafted = _tar_gz(sorted(members.items()))
        with pytest.raises(BundleHashMismatch, match="slots.ts"):
            verify_bundle(crafted, sign(crafted), trust_root)

    def test_a_resolved_document_that_does_not_rederive_its_hash_is_refused(
        self, archive: bytes, sign: Callable[[bytes], bytes], trust_root: TrustRoot
    ) -> None:
        members = _members(archive)
        document = json.loads(members[RESOLVED])
        document["title_tr"] = "Sessizce değiştirildi"
        members[RESOLVED] = json.dumps(document, sort_keys=True, ensure_ascii=False).encode()
        crafted = _tar_gz(sorted(_rehash_manifest(members).items()))
        with pytest.raises(BundleHashMismatch, match="resolved"):
            verify_bundle(crafted, sign(crafted), trust_root)

    def test_a_manifest_naming_another_pack_than_its_document_is_refused(
        self, archive: bytes, sign: Callable[[bytes], bytes], trust_root: TrustRoot
    ) -> None:
        members = _members(archive)
        manifest = json.loads(members[MANIFEST])
        manifest["pack_id"] = "base.baska"
        members[MANIFEST] = json.dumps(manifest).encode()
        crafted = _tar_gz(sorted(members.items()))
        with pytest.raises(BundleArchiveMalformed, match="base.baska"):
            verify_bundle(crafted, sign(crafted), trust_root)

    @pytest.mark.parametrize(
        "build",
        [
            lambda m: _tar_gz([(n, d) for n, d in sorted(m.items()) if n != MANIFEST]),
            lambda m: _tar_gz([(n, d) for n, d in sorted(m.items()) if n != RESOLVED]),
            lambda m: _tar_gz(
                sorted(_rehash_manifest({k: v for k, v in m.items() if k != RESOLVED}).items())
            ),
            lambda m: _tar_gz([*sorted(m.items()), ("fazla.json", b"{}")]),
            lambda m: _tar_gz([*sorted(m.items()), ("slots.ts", b"")]),
            lambda m: _tar_gz([*sorted(m.items()), ("../disari.json", b"{}")]),
            lambda m: _tar_gz([*sorted(m.items()), ("alt/icerik.json", b"{}")]),
            lambda m: _tar_gz(sorted({**m, MANIFEST: b"{not json"}.items())),
            lambda m: _tar_gz(
                sorted(_rehash_manifest({**m, RESOLVED: b'{"pack_id": "eksik"}'}).items())
            ),
            lambda m: _tar_gz(sorted(m.items()), extra=(_symlink("baglanti.json"),)),
            lambda m: _tar_gz(sorted(m.items()), extra=(_directory("dizin"),)),
            lambda m: b"duz metin, gzip degil",
            lambda m: gzip.compress(b"gzip ama tar degil" * 64, mtime=0),
        ],
        ids=[
            "no-manifest",
            "resolved-missing-from-members",
            "resolved-missing-everywhere",
            "unlisted-member",
            "duplicate-member",
            "parent-traversal",
            "nested-path",
            "manifest-not-json",
            "resolved-not-a-document",
            "symlink",
            "directory",
            "not-gzip",
            "not-tar",
        ],
    )
    def test_a_signed_archive_of_the_wrong_shape_is_refused(
        self,
        archive: bytes,
        sign: Callable[[bytes], bytes],
        trust_root: TrustRoot,
        build: Callable[[dict[str, bytes]], bytes],
    ) -> None:
        crafted = build(_members(archive))
        with pytest.raises(BundleArchiveMalformed):
            verify_bundle(crafted, sign(crafted), trust_root)

    def test_a_truncated_gzip_stream_is_refused(
        self, archive: bytes, sign: Callable[[bytes], bytes], trust_root: TrustRoot
    ) -> None:
        crafted = archive[: len(archive) - 12]
        with pytest.raises(BundleArchiveMalformed, match="truncated"):
            verify_bundle(crafted, sign(crafted), trust_root)

    def test_trailing_bytes_after_the_gzip_stream_are_refused(
        self, archive: bytes, sign: Callable[[bytes], bytes], trust_root: TrustRoot
    ) -> None:
        crafted = archive + gzip.compress(b"ikinci uye", mtime=0)
        with pytest.raises(BundleArchiveMalformed, match="trailing"):
            verify_bundle(crafted, sign(crafted), trust_root)

    def test_an_archive_that_inflates_past_the_bound_is_refused(
        self,
        archive: bytes,
        sign: Callable[[bytes], bytes],
        trust_root: TrustRoot,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(trust, "MAX_UNPACKED_BYTES", 1024)
        with pytest.raises(BundleArchiveMalformed, match="inflates"):
            verify_bundle(archive, sign(archive), trust_root)

    def test_an_oversized_archive_is_refused_before_it_is_read(
        self,
        tmp_path: Path,
        bundle: CompiledBundle,
        sign: Callable[[bytes], bytes],
        trust_root: TrustRoot,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        write_bundle(bundle, tmp_path)
        path = tmp_path / PACK_ID / BUNDLE_ARCHIVE
        path.with_name(BUNDLE_ARCHIVE + SIGNATURE_SUFFIX).write_bytes(sign(path.read_bytes()))
        monkeypatch.setattr(trust, "MAX_ARCHIVE_BYTES", 16)
        with pytest.raises(BundleArchiveMalformed, match="larger"):
            load_verified_bundle(path, trust_root)
        with pytest.raises(BundleArchiveMalformed, match="larger"):
            verify_bundle(path.read_bytes(), sign(path.read_bytes()), trust_root)

    def test_every_refusal_is_one_typed_family(self) -> None:
        for refusal in (
            TrustRootMissing,
            TrustRootInvalid,
            BundleUnsigned,
            BundleSignatureInvalid,
            BundleUntrustedSigner,
            BundleHashMismatch,
            BundleArchiveMalformed,
        ):
            assert issubclass(refusal, BundleRefused)
            assert refusal.reason
        assert len({r.reason for r in BundleRefused.__subclasses__()}) == len(
            BundleRefused.__subclasses__()
        )

    def test_a_verified_bundle_is_minted_only_by_the_verifier(
        self, archive: bytes, sign: Callable[[bytes], bytes], trust_root: TrustRoot
    ) -> None:
        verified = verify_bundle(archive, sign(archive), trust_root)
        with pytest.raises(TypeError, match="verify_bundle"):
            VerifiedBundle(
                token=object(),
                manifest=verified.manifest,
                protocol=verified.protocol,
                artifacts=dict(verified.artifacts),
                archive_sha256=verified.archive_sha256,
                signer_key_id=verified.signer_key_id,
            )
        with pytest.raises(TypeError):
            verified.artifacts["slots.ts"] = b""  # type: ignore[index]


def _symlink(name: str) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.type = tarfile.SYMTYPE
    info.linkname = "manifest.json"
    return info


def _directory(name: str) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.type = tarfile.DIRTYPE
    return info


# =================================================================== 3. the trust root


class TestTheTrustRootFailsClosed:
    def test_no_configured_trust_root_refuses_and_names_int_019(self) -> None:
        with pytest.raises(TrustRootMissing, match="INT-019"):
            load_trust_root({})
        with pytest.raises(TrustRootMissing, match="INT-019"):
            load_trust_root({TRUST_ROOT_ENV: "   "})

    def test_the_process_environment_is_the_default_source(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv(TRUST_ROOT_ENV, raising=False)
        with pytest.raises(TrustRootMissing):
            load_trust_root()

    def test_an_unreadable_trust_root_path_refuses(self, tmp_path: Path) -> None:
        with pytest.raises(TrustRootMissing, match="cannot be read"):
            load_trust_root({TRUST_ROOT_ENV: str(tmp_path / "yok.pub")})

    def test_a_configured_public_key_loads_with_a_stable_key_id(
        self, tmp_path: Path, signing_key: ec.EllipticCurvePrivateKey
    ) -> None:
        pem = _public_pem(signing_key)
        path = tmp_path / "protocol-bundles.pub"
        path.write_bytes(pem)
        root = load_trust_root({TRUST_ROOT_ENV: str(path)})
        der = signing_key.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        assert root.key_id == hashlib.sha256(der).hexdigest()
        assert root.key_id == TrustRoot.from_pem(pem).key_id

    @pytest.mark.parametrize(
        "pem",
        [
            lambda: b"bu bir anahtar degil",
            lambda: _public_pem(rsa.generate_private_key(public_exponent=65537, key_size=2048)),
            lambda: _public_pem(ec.generate_private_key(ec.SECP384R1())),
            lambda: _new_key().private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            ),
        ],
        ids=["garbage", "rsa", "p384", "private-half"],
    )
    def test_anything_but_a_p256_public_key_is_refused(self, pem: Callable[[], bytes]) -> None:
        with pytest.raises(TrustRootInvalid):
            TrustRoot.from_pem(pem())


# =================================================================== 4. the per-session pin


@pytest.fixture
def served(
    bundle: CompiledBundle, sign: Callable[[bytes], bytes], trust_root: TrustRoot
) -> tuple[ServedBundles, VerifiedBundle]:
    archive = bundle_archive(bundle)
    verified = verify_bundle(archive, sign(archive), trust_root)
    shelf = ServedBundles()
    shelf.deploy(verified)
    return shelf, verified


@pytest.fixture
def second(
    tightened: CompiledBundle, sign: Callable[[bytes], bytes], trust_root: TrustRoot
) -> VerifiedBundle:
    archive = bundle_archive(tightened)
    return verify_bundle(archive, sign(archive), trust_root)


class TestTheHashIsPinnedPerSession:
    def test_a_session_keeps_its_hash_when_a_new_bundle_is_deployed(
        self, served: tuple[ServedBundles, VerifiedBundle], second: VerifiedBundle
    ) -> None:
        shelf, first = served
        assert first.resolved_protocol_hash != second.resolved_protocol_hash
        started = shelf.pin("ses-bir", KEY)
        assert started.protocol_hash == first.resolved_protocol_hash

        shelf.deploy(second)

        assert shelf.current(KEY) is second
        assert shelf.pinned("ses-bir").protocol_hash == first.resolved_protocol_hash
        assert shelf.pinned("ses-bir").bundle is first
        assert shelf.pin("ses-bir", KEY) == started
        assert shelf.pin("ses-iki", KEY).protocol_hash == second.resolved_protocol_hash

    def test_the_pin_hands_the_composition_root_its_protocol_and_hash(
        self, served: tuple[ServedBundles, VerifiedBundle]
    ) -> None:
        shelf, first = served
        pin = shelf.pin("ses-bir", KEY)
        assert pin.session_id == "ses-bir"
        assert pin.key == KEY
        assert pin.protocol is first.protocol
        assert pin.archive_sha256 == first.archive_sha256
        state = SessionState(
            session_id="ses-bir",
            protocol_id=pin.protocol.pack_id,
            protocol_version=pin.protocol.version,
            protocol_hash=pin.protocol_hash,
            mode="fast",
            status="active",
            reference_time=datetime.datetime(2026, 9, 26, tzinfo=datetime.UTC),
            budget=SessionBudget(turns_used=0, turns_remaining=18),
        )
        assert state.protocol_hash == first.resolved_protocol_hash

    def test_nothing_deployed_means_nothing_to_pin(self, trust_root: TrustRoot) -> None:
        shelf = ServedBundles()
        with pytest.raises(UnknownBundle):
            shelf.pin("ses-bir", KEY)
        with pytest.raises(UnknownBundle):
            shelf.current(KEY)
        with pytest.raises(SessionNotPinned):
            shelf.pinned("ses-bir")

    def test_a_session_cannot_be_repinned_to_another_pack(
        self, served: tuple[ServedBundles, VerifiedBundle]
    ) -> None:
        shelf, _ = served
        shelf.pin("ses-bir", KEY)
        other = BundleKey(pack_id="base.baska", locale=LOCALE, voice=VOICE)
        with pytest.raises(PinConflict):
            shelf.pin("ses-bir", other)

    def test_a_resumed_session_never_falls_forward_to_the_current_bundle(
        self, served: tuple[ServedBundles, VerifiedBundle], second: VerifiedBundle
    ) -> None:
        _, first = served
        # a restarted process that has only the new bundle deployed
        restarted = ServedBundles()
        restarted.deploy(second)
        with pytest.raises(UnknownBundle, match="never falls forward"):
            restarted.resume("ses-bir", KEY, first.resolved_protocol_hash)
        # re-admitting the old version (not deploying it) is what resumes it
        restarted.admit(first)
        resumed = restarted.resume("ses-bir", KEY, first.resolved_protocol_hash)
        assert resumed.bundle is first
        assert restarted.current(KEY) is second
        assert restarted.resume("ses-bir", KEY, first.resolved_protocol_hash) == resumed
        with pytest.raises(PinConflict):
            restarted.resume("ses-bir", KEY, second.resolved_protocol_hash)

    def test_a_released_session_frees_its_pin(
        self, served: tuple[ServedBundles, VerifiedBundle]
    ) -> None:
        shelf, _ = served
        shelf.pin("ses-bir", KEY)
        shelf.release("ses-bir")
        with pytest.raises(SessionNotPinned):
            shelf.pinned("ses-bir")
        shelf.release("ses-bir")

    def test_only_a_verified_bundle_can_be_served(self) -> None:
        shelf = ServedBundles()
        with pytest.raises(TypeError, match="VerifiedBundle"):
            shelf.deploy(object())  # type: ignore[arg-type]
        with pytest.raises(TypeError, match="VerifiedBundle"):
            shelf.admit({"resolved_protocol_hash": "0" * 64})  # type: ignore[arg-type]

    def test_a_published_version_is_byte_immutable(
        self,
        served: tuple[ServedBundles, VerifiedBundle],
        bundle: CompiledBundle,
        sign: Callable[[bytes], bytes],
        trust_root: TrustRoot,
    ) -> None:
        shelf, first = served
        shelf.admit(first)  # the same bytes again is a no-op
        members = _members(bundle_archive(bundle))
        members["slots.ts"] = members["slots.ts"] + b"// ayni hash, baska bayt\n"
        crafted = _tar_gz(sorted(_rehash_manifest(members).items()))
        same_hash_other_bytes = verify_bundle(crafted, sign(crafted), trust_root)
        assert same_hash_other_bytes.resolved_protocol_hash == first.resolved_protocol_hash
        with pytest.raises(PublishedVersionConflict):
            shelf.deploy(same_hash_other_bytes)
        assert shelf.current(KEY) is first


# =================================================================== 5. the note meta


class TestTheNoteMetaShowsThePinnedHash:
    def test_each_session_note_shows_the_hash_it_was_pinned_to(
        self, served: tuple[ServedBundles, VerifiedBundle], second: VerifiedBundle
    ) -> None:
        shelf, first = served
        early = shelf.pin("ses-bir", KEY)
        shelf.deploy(second)
        late = shelf.pin("ses-iki", KEY)

        copy = note_copy_from_legal_strings(
            LegalStringsCatalog(SYNTHETIC_STRINGS).entry(required=NOTE_COPY_KEYS)
        )
        rendered = {}
        for pin in (early, late):
            meta = NoteMeta(
                visit_id=f"visit-{pin.session_id}",
                protocol_hash=pin.protocol_hash,
                mode="fast",
                generated_at=datetime.datetime(2026, 9, 26, 9, 0, tzinfo=datetime.UTC),
                model="synthetic-note-model@rev0",
                prompt_version="note-v0",
            )
            composed = compose(
                meta=meta,
                triage=RulesTriageResult(level=TriageLevel.GREEN),
                screening=ScreeningBlock(
                    provenance=ScreeningProvenance(
                        administration_mode="typed",
                        proxy_reported=False,
                        third_party_present=False,
                    )
                ),
            )
            assert composed.note.meta.protocol_hash == pin.protocol_hash
            rendered[pin.session_id] = render_soap(composed, copy)

        assert f"protocol_hash: {first.resolved_protocol_hash}" in rendered["ses-bir"]
        assert f"protocol_hash: {second.resolved_protocol_hash}" in rendered["ses-iki"]
        assert second.resolved_protocol_hash not in rendered["ses-bir"]
