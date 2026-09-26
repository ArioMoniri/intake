"""INT-058 — the resolved-protocol hash, pinned per session.

files/04 §7: *"the resolved-protocol hash is pinned per session and shown in
the note meta"*; files/03 §6: *"resolved-protocol hash stored on every
session"*. The acceptance's operational reading: a session started on hash H
keeps H even when a new bundle is deployed mid-session.

:class:`ServedBundles` is the runtime's shelf of verified bundles. It holds
three maps and no other state:

- **admitted** — every verified bundle this process may serve, addressed by
  ``(BundleKey, resolved_protocol_hash)``. A version stays here after a newer
  one is deployed, because sessions pinned to it are still running. It is
  byte-immutable: the same address with different archive bytes is refused
  (files/10 §8 inv. 41 — "a published version that has served a session is
  byte-immutable").
- **current** — the version a *new* session starts on, per key.
- **pins** — session id → the bundle it started on. :meth:`pin` is
  idempotent, and a later deploy never touches an existing pin.

:meth:`resume` is the restart path. The session's persisted
``SessionState.protocol_hash`` names the version; if that version has not been
re-admitted, resuming refuses. It **never falls forward** to the current
bundle: continuing a session on a protocol it did not start on would make the
recorded hash, the note meta and the re-triage sweep all describe a different
document from the one the patient answered.

Only a :class:`~protocols.serving.trust.VerifiedBundle` can enter the shelf,
and only :func:`~protocols.serving.trust.verify_bundle` mints one — so an
unsigned or tampered bundle has no path to a session.

Quarantine and the ``known_good`` fallback (files/10 §8 inv. 44) are the pack
lifecycle issues' (INT-184); this shelf deliberately has no un-publish verb.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from protocols.compile.resolve import ResolvedProtocol
from protocols.serving.trust import BundleKey, VerifiedBundle

__all__ = [
    "BundleKey",
    "PinConflict",
    "PinError",
    "PublishedVersionConflict",
    "ServedBundles",
    "SessionNotPinned",
    "SessionPin",
    "UnknownBundle",
]


class PinError(Exception):
    """A pin the shelf cannot honour. Every subclass fails closed."""


class UnknownBundle(PinError, LookupError):
    """No verified bundle is admitted for this key (or this key and hash)."""


class SessionNotPinned(PinError, LookupError):
    """The session has no pin; it was never started or was released."""


class PinConflict(PinError):
    """The session is already pinned to a different pack or version."""


class PublishedVersionConflict(PinError):
    """Different bytes under an already-admitted (key, resolved hash)."""


@dataclass(frozen=True)
class SessionPin:
    """One session's protocol, fixed at start. Two pins are equal only when
    they hold the same session and the very same verified bundle object."""

    session_id: str
    bundle: VerifiedBundle

    @property
    def key(self) -> BundleKey:
        return self.bundle.key

    @property
    def protocol_hash(self) -> str:
        """``SessionState.protocol_hash``, ``TalkerConfig.protocol_hash`` and
        ``NoteMeta.protocol_hash`` for this session — one value, three places."""
        return self.bundle.resolved_protocol_hash

    @property
    def protocol(self) -> ResolvedProtocol:
        """The document the composition root runs this session on."""
        return self.bundle.protocol

    @property
    def archive_sha256(self) -> str:
        return self.bundle.archive_sha256


class ServedBundles:
    """Verified bundles, the current deployment per key, and per-session pins."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._admitted: dict[tuple[BundleKey, str], VerifiedBundle] = {}
        self._current: dict[BundleKey, VerifiedBundle] = {}
        self._pins: dict[str, SessionPin] = {}

    def admit(self, bundle: VerifiedBundle) -> None:
        """Make a verified version resolvable by hash without deploying it."""
        if not isinstance(bundle, VerifiedBundle):
            raise TypeError("only a VerifiedBundle (minted by verify_bundle) can be served")
        with self._lock:
            self._admit(bundle)

    def deploy(self, bundle: VerifiedBundle) -> None:
        """Admit ``bundle`` and make it the version new sessions start on.

        Existing pins are untouched: that is the whole point of a pin.
        """
        if not isinstance(bundle, VerifiedBundle):
            raise TypeError("only a VerifiedBundle (minted by verify_bundle) can be served")
        with self._lock:
            self._admit(bundle)
            self._current[bundle.key] = bundle

    def current(self, key: BundleKey) -> VerifiedBundle:
        with self._lock:
            return self._current_for(key)

    def pin(self, session_id: str, key: BundleKey) -> SessionPin:
        """Pin a starting session to the current bundle, once."""
        with self._lock:
            existing = self._pins.get(session_id)
            if existing is not None:
                if existing.key != key:
                    raise PinConflict(
                        f"session {session_id} is pinned to {existing.key}, not {key}"
                    )
                return existing
            pin = SessionPin(session_id=session_id, bundle=self._current_for(key))
            self._pins[session_id] = pin
            return pin

    def resume(self, session_id: str, key: BundleKey, protocol_hash: str) -> SessionPin:
        """Re-pin a session to the exact version its state records."""
        with self._lock:
            existing = self._pins.get(session_id)
            if existing is not None:
                if (existing.key, existing.protocol_hash) != (key, protocol_hash):
                    raise PinConflict(
                        f"session {session_id} is pinned to {existing.key} at "
                        f"{existing.protocol_hash}, not {protocol_hash}"
                    )
                return existing
            bundle = self._admitted.get((key, protocol_hash))
            if bundle is None:
                raise UnknownBundle(
                    f"session {session_id} started on {protocol_hash}, which is not admitted "
                    f"for {key}; a session never falls forward to the current bundle — "
                    "re-admit the version it started on"
                )
            pin = SessionPin(session_id=session_id, bundle=bundle)
            self._pins[session_id] = pin
            return pin

    def pinned(self, session_id: str) -> SessionPin:
        with self._lock:
            pin = self._pins.get(session_id)
        if pin is None:
            raise SessionNotPinned(f"session {session_id} has no protocol pin")
        return pin

    def release(self, session_id: str) -> None:
        """Drop a finished session's pin. Idempotent."""
        with self._lock:
            self._pins.pop(session_id, None)

    def _admit(self, bundle: VerifiedBundle) -> None:
        address = (bundle.key, bundle.resolved_protocol_hash)
        held = self._admitted.get(address)
        if held is not None and held.archive_sha256 != bundle.archive_sha256:
            raise PublishedVersionConflict(
                f"{bundle.key} at {bundle.resolved_protocol_hash} is already admitted as "
                f"archive {held.archive_sha256}; a published version is byte-immutable"
            )
        self._admitted[address] = held if held is not None else bundle

    def _current_for(self, key: BundleKey) -> VerifiedBundle:
        bundle = self._current.get(key)
        if bundle is None:
            raise UnknownBundle(f"no verified bundle is deployed for {key}")
        return bundle
