"""The signable form of a compiled bundle: one deterministic ``bundle.tar.gz``.

INT-058's acceptance opens with *"compiler emits bundle.tar.gz signed"*, and
files/04 §7 says what is in it: *"a bundle (YAML + compiled outputs + clip
manifest) signed with cosign"*. The archive holds every artefact
:func:`~protocols.compile.bundle.compile_bundle` produced — the five files/03
§6 outputs, the ``manifest.json`` that hashes each of them, and
``resolved_protocol.json``, the merged document the resolved-protocol hash is
computed over. The runtime needs nothing outside it.

**Deterministic by construction, like the loose artefacts.** Members are
written in name order as USTAR regular files with every build-machine field
zeroed (mtime, uid, gid, owner names) and one fixed mode; the gzip header
carries no file name and a zero timestamp. Two compiles of the same inputs
therefore produce the same archive bytes on one toolchain, and the digest
recorded beside it is stable. Integrity never *depends* on that, though: what
the runtime trusts is a signature over whatever bytes were signed, and the
manifest's per-artefact hashes identify the content independently of how
zlib chose to compress it.

**Signing is not done here.** No private key ever enters this process: `make
sign` hands each archive to ``cosign sign-blob`` with an operator-supplied key
reference, and cosign writes ``bundle.tar.gz.sigstore.json`` beside it. The
reference, and so the key's custody, belongs to INT-019 (awaiting the owner).
"""

from __future__ import annotations

import gzip
import hashlib
import io
import tarfile
from pathlib import Path
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from protocols.compile.bundle import CompiledBundle

__all__ = [
    "BUNDLE_ARCHIVE",
    "DIGEST_SUFFIX",
    "SIGNATURE_SUFFIX",
    "archive_sha256",
    "bundle_archive",
    "write_archive",
]

BUNDLE_ARCHIVE: Final = "bundle.tar.gz"
"""The acceptance's own name for the signable archive (INT-058)."""

DIGEST_SUFFIX: Final = ".sha256"
"""``bundle.tar.gz.sha256`` in ``sha256sum`` format, for a human's ``-c`` check."""

SIGNATURE_SUFFIX: Final = ".sigstore.json"
"""What ``cosign sign-blob --bundle`` writes beside the archive: a sigstore
bundle carrying the message signature (see ``make sign``)."""

_MEMBER_MODE: Final = 0o644


def bundle_archive(bundle: CompiledBundle) -> bytes:
    """Every artefact of ``bundle`` as one reproducible gzip'd USTAR archive."""
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        for name, content in sorted(bundle.artifacts.items()):
            data = content.encode("utf-8")
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mtime = 0
            info.mode = _MEMBER_MODE
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.type = tarfile.REGTYPE
            tar.addfile(info, io.BytesIO(data))
    compressed = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=compressed, mtime=0) as stream:
        stream.write(raw.getvalue())
    return compressed.getvalue()


def archive_sha256(archive: bytes) -> str:
    """Lower-case hex sha256 — the digest cosign's message signature declares."""
    return hashlib.sha256(archive).hexdigest()


def write_archive(bundle: CompiledBundle, target: Path) -> tuple[Path, Path]:
    """Write ``bundle.tar.gz`` and its ``.sha256`` sidecar into ``target``."""
    archive = bundle_archive(bundle)
    archive_path = target / BUNDLE_ARCHIVE
    archive_path.write_bytes(archive)
    digest_path = target / (BUNDLE_ARCHIVE + DIGEST_SUFFIX)
    digest_path.write_text(f"{archive_sha256(archive)}  {BUNDLE_ARCHIVE}\n", encoding="ascii")
    return archive_path, digest_path
