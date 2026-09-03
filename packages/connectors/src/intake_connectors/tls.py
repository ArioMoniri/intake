"""mTLS for connector pushes: material from OpenBao, never a file on disk.

``ssl.SSLContext.load_cert_chain`` is the only way Python loads a client
certificate and it takes **paths**, not bytes — there is no in-memory API in
the standard library. So the private key must be readable through a file
descriptor for the length of one call, and the whole job of this module is to
make that window as small and as unobservable as it can be:

- the material is written into a directory this process creates with mode
  ``0700`` and a file created with mode ``0600`` (``O_CREAT|O_EXCL``), so no
  other user and no other service ever has a path to it;
- ``load_cert_chain`` reads it once, after which the bytes are overwritten
  with zeros and the file is unlinked — in a ``finally``, so a failure to load
  cleans up exactly like a success;
- the material never reaches a log: :class:`~intake_connectors.credentials.TlsMaterial`
  has no representation containing its own bytes, and nothing here formats it.

The context also pins the boring parts: TLS 1.2 floor, hostname checking on,
default CA store. The INT-018 guard has already resolved and pinned the
address by the time this context is used, and it passes the hostname through
as SNI, so certificate verification is against the name — pinning removed a
DNS lookup, not a check.
"""

from __future__ import annotations

import os
import ssl
import tempfile
from pathlib import Path

import httpx

from intake_connectors.credentials import TlsMaterial

__all__ = ["mtls_context", "mtls_transport"]


def _write_private(directory: Path, name: str, content: str) -> Path:
    path = directory / name
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(content.encode("utf-8"))
    return path


def _shred(path: Path) -> None:
    try:
        size = path.stat().st_size
        with path.open("r+b") as handle:
            handle.write(b"\0" * size)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError:  # pragma: no cover - the unlink below is the real guarantee
        pass
    finally:
        path.unlink(missing_ok=True)


def mtls_context(material: TlsMaterial) -> ssl.SSLContext:
    """An ``SSLContext`` holding the client certificate, leaving no file behind."""
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    with tempfile.TemporaryDirectory(prefix="intake-mtls-") as raw_directory:
        directory = Path(raw_directory)
        directory.chmod(0o700)
        certificate = _write_private(directory, "client.crt", material.certificate)
        key = _write_private(directory, "client.key", material.private_key)
        try:
            context.load_cert_chain(certfile=certificate, keyfile=key)
        finally:
            _shred(key)
            _shred(certificate)
    return context


def mtls_transport(material: TlsMaterial) -> httpx.BaseTransport:
    """The production transport factory the sender takes by default."""
    return httpx.HTTPTransport(verify=mtls_context(material))
