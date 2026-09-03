"""Connector credentials: OpenBao at send time, and nothing that renders itself.

CLAUDE.md invariant 14: secrets come from OpenBao, never from a file, an
environment variable or a row in this repository. The registry holds a *path*;
:class:`CredentialResolver` turns it into material for the duration of one
send.

The second half is the part that gets forgotten. A credential does not leak
because someone logged it deliberately — it leaks because a dataclass grew a
default ``__repr__``, an exception got formatted with ``!r``, or a failing
request was dumped "for debugging". :class:`TlsMaterial` therefore has no
representation that contains its own bytes, and :class:`CredentialMissing`
names no path: an error message travels further than the code that raised it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from intake_platform.secrets import SecretsProvider

__all__ = [
    "CredentialMissing",
    "CredentialResolver",
    "InMemoryCredentialResolver",
    "OpenBaoCredentialResolver",
    "TlsMaterial",
]

_REDACTED = "<redacted>"


class CredentialMissing(Exception):
    """No material is available for a destination's credential reference.

    The reference is deliberately absent from the message. It is an OpenBao
    path, and a path in an error string is a map of the secret store handed to
    whoever reads the log.
    """


@dataclass(frozen=True, repr=False)
class TlsMaterial:
    """A client certificate and its private key, for mTLS.

    ``repr`` and ``str`` are overridden together: overriding only ``__repr__``
    leaves ``f"{material}"`` printing the key, which is the exact call site
    that leaks it.
    """

    certificate: str
    private_key: str

    def __repr__(self) -> str:
        return f"TlsMaterial(certificate={_REDACTED}, private_key={_REDACTED})"

    def __str__(self) -> str:
        return self.__repr__()


class CredentialResolver(Protocol):
    """Reads one credential document by its OpenBao path."""

    def read(self, ref: str) -> Mapping[str, str]: ...


class InMemoryCredentialResolver:
    """The unit-lane resolver: a mapping behind the protocol.

    Test material only. Nothing constructs this outside tests, which is what
    keeps invariant 17's "mocks live in tests only" true for this seam.
    """

    def __init__(self, documents: Mapping[str, Mapping[str, str]]) -> None:
        self._documents = {ref: dict(document) for ref, document in documents.items()}

    def read(self, ref: str) -> Mapping[str, str]:
        try:
            return self._documents[ref]
        except KeyError:
            raise CredentialMissing("no credential material for this destination") from None


class OpenBaoCredentialResolver:
    """The production resolver: OpenBao KV v2 through the INT-017 client."""

    def __init__(self, provider: SecretsProvider) -> None:
        self._provider = provider

    def read(self, ref: str) -> Mapping[str, str]:
        try:
            document = self._provider.get_kv(ref)
        except Exception:  # noqa: BLE001 - the cause carries the path; it must not escape
            raise CredentialMissing("no credential material for this destination") from None
        return {key: str(value) for key, value in document.items()}


def require_keys(document: Mapping[str, str], *keys: str) -> tuple[str, ...]:
    """Pull the named keys, or fail closed with a message naming neither the
    path nor any value that was present."""
    values: list[str] = []
    for key in keys:
        value = document.get(key)
        if not value:
            raise CredentialMissing(
                f"the credential document for this destination has no {key!r} entry"
            )
        values.append(value)
    return tuple(values)
