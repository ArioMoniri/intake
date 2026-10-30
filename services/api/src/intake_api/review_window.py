"""INT-488 — the App Review window and the live facts a reviewer depends on (D39).

**The window** (:class:`ReviewWindow`) is one Redis document the owner flips
with ``python -m intake_api.review_cli on|off``. Absent is closed, the
default, and so is anything that is not exactly an open document. Each opening
carries a fresh random ``id``: the reviewer patient of that window is derived
from it, and every reviewer session is bound to it, so a token from one review
never works in the next and no reviewer sees another's data.

**A window ends by itself** :data:`REVIEW_WINDOW_S` after it opened (14 days,
an engineering default the owner may change in a reviewed diff). From that
instant every reader treats it as closed, before anything else happens (fail
closed); the API then closes it the way ``--off`` does — the document first,
the audit row second, the reviewer tenant's erasure last — on the next reviewer
step or its own sweep, whichever comes first. Nothing reopens it: that takes a
fresh ``--on``.

**The live guards** (:class:`ReviewGuards`) are read on every reviewer step,
beside the window, and fail closed:

- the deployment's *bound* data class (ADR-035): a model-lane control record
  bound ``real_phi`` makes a host that held real patients refuse the reviewer,
  whatever the image declares; an unreadable record reads ``real_phi``;
- hosted model lanes off for the reviewer's tenant. The reviewer is a real
  person, and the synthetic data class would otherwise let a hosted lane carry
  what they type as non-personal (security review, 30 Oct 2026). The INT-182
  kill switch of the reviewer tenant, which the model-lane router reads, must
  read engaged; no voice-control store, or an unreadable one, refuses.
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

import redis
from intake_platform.model_lanes.guard import effective_data_class
from intake_platform.model_lanes.model import TenantDataClass
from intake_platform.model_lanes.store import ModelLanesReader, ModelLanesUnavailable
from intake_platform.voice_control.store import VoiceControlReader, VoiceControlUnavailable

__all__ = [
    "REVIEW_TENANT_ID",
    "REVIEW_WINDOW_S",
    "ReviewGuards",
    "ReviewWindow",
    "ReviewWindowUnreadable",
    "WindowState",
    "review_patient",
]

logger = logging.getLogger("intake_api.review_signin")

#: The reviewer's own tenant: a fixed UUIDv5 key, so the bootstrap is idempotent.
REVIEW_TENANT_ID: Final = uuid.uuid5(uuid.NAMESPACE_URL, "https://intake.app/tenants/app-review")
_WINDOW_ID_BYTES: Final = 16
#: How long a review window stays open after ``--on``. An engineering default
#: (the orchestrator's, 30 Oct 2026), not D39's and not a clinical value: long
#: enough for an App Review round and its resubmission, short enough that a
#: window nobody closed still ends. The owner may change it in a reviewed diff.
REVIEW_WINDOW_S: Final = 14 * 24 * 3600


def review_patient(window_id: str) -> tuple[uuid.UUID, str]:
    """The synthetic reviewer patient of one window: a UUIDv5 id and a
    pseudonym from a fixed synthetic label (the ``review`` kid marks it: no
    HMAC key and no identifier behind it), the dev fixture's pattern. One per
    window, so a reviewer never lands in an earlier reviewer's record."""
    label = f"intake-app-review-reviewer:{window_id}"
    patient_id = uuid.uuid5(uuid.NAMESPACE_URL, f"https://intake.app/patients/{label}")
    return patient_id, "review." + hashlib.sha256(label.encode("ascii")).hexdigest()


class ReviewWindowUnreadable(Exception):
    """The window could not be read. Every reader treats it as closed."""


@dataclass(frozen=True)
class WindowState:
    since: float
    id: str

    @property
    def closes_at(self) -> float:
        return self.since + REVIEW_WINDOW_S


class ReviewWindow:
    """The review-window switch, one Redis document."""

    def __init__(
        self,
        redis_client: redis.Redis,
        now_fn: Callable[[], float] | None = None,
        key_prefix: str = "auth",
    ) -> None:
        self._r = redis_client
        self._now_fn = now_fn
        self._key = f"{key_prefix}:review:window"

    def _now(self) -> float:
        return self._now_fn() if self._now_fn is not None else time.time()

    def state(self) -> WindowState | None:
        """The open state, or None when closed. Raises
        :class:`ReviewWindowUnreadable` when the store cannot answer."""
        try:
            raw = self._r.get(self._key)
        except redis.RedisError:
            raise ReviewWindowUnreadable("the review window is unreadable") from None
        if raw is None:
            return None
        try:
            document = json.loads(raw)
            if document["state"] != "open":
                return None
            window_id = document["id"]
            if not isinstance(window_id, str) or len(window_id) != 2 * _WINDOW_ID_BYTES:
                return None
            return WindowState(since=float(document["since"]), id=window_id)
        except (ValueError, KeyError, TypeError):
            return None

    def expired(self, state: WindowState) -> bool:
        return self._now() >= state.closes_at

    def remaining(self, state: WindowState) -> float:
        return max(state.closes_at - self._now(), 0.0)

    def current(self) -> WindowState | None:
        """The open window, or None for closed, expired, garbled or unreadable."""
        try:
            state = self.state()
        except ReviewWindowUnreadable:
            logger.warning("review sign-in refused: the review window is unreadable")
            return None
        return None if state is None or self.expired(state) else state

    def due_for_expiry(self) -> WindowState | None:
        """The window whose time has run out and which is still stored, or None."""
        try:
            state = self.state()
        except ReviewWindowUnreadable:
            return None
        return state if state is not None and self.expired(state) else None

    def is_open(self) -> bool:
        return self.current() is not None

    def open(self) -> bool:
        """Open a new window with a fresh id. True when this call opened it."""
        document = {
            "state": "open",
            "since": self._now(),
            "id": secrets.token_hex(_WINDOW_ID_BYTES),
        }
        return bool(self._r.set(self._key, json.dumps(document), nx=True))

    def close(self, expect_id: str | None = None) -> bool:
        """Close the window. True when it held anything. With ``expect_id``,
        only that window, in one transaction: an expiry never closes a fresh
        window the owner opened a moment before."""
        if expect_id is None:
            return bool(self._r.delete(self._key))
        try:
            with self._r.pipeline() as pipe:
                pipe.watch(self._key)  # type: ignore[no-untyped-call]  # redis-py leaves watch unannotated
                raw = pipe.get(self._key)
                document = json.loads(raw) if raw is not None else None
                if not isinstance(document, dict) or document.get("id") != expect_id:
                    return False
                pipe.multi()
                pipe.delete(self._key)
                pipe.execute()
        except (redis.WatchError, ValueError):
            return False
        return True


@dataclass(frozen=True)
class ReviewGuards:
    """The live facts besides the window. ``None`` for the lane store means
    the deployment has no model-lane control, so nothing can be bound and the
    declared class stands (ADR-035); ``None`` for the voice store means nothing
    can switch hosted lanes off for the reviewer, which refuses."""

    lanes: ModelLanesReader | None = None
    voice: VoiceControlReader | None = None

    def refusal(self) -> str | None:
        if self.lanes is not None:
            try:
                bound = self.lanes.read().data_class
            except ModelLanesUnavailable:
                bound = TenantDataClass.REAL_PHI
            if effective_data_class(TenantDataClass.SYNTHETIC, bound) is not (
                TenantDataClass.SYNTHETIC
            ):
                return "not_synthetic"
        if self.voice is None:
            return "hosted_lanes_open"
        try:
            engaged = self.voice.read(str(REVIEW_TENANT_ID)).kill_switch
        except VoiceControlUnavailable:
            engaged = False
        return None if engaged else "hosted_lanes_open"
