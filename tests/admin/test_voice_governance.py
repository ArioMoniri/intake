"""INT-182 — the voice control record, its store and its governor, below the routes.

``test_kill_switch.py`` proves the acceptance end to end through
``/admin/voice/*`` and the runtime. This file pins the pieces it rests on, each
with its near-miss:

- **The record cannot hold an impossible state** — a canary with no profile, a
  canary of the default, a canary profile at weight 0, a staff subject shaped
  like prose.
- **The store fails closed and loudly** — unreachable and malformed are codes,
  never a default; a write moves the revision by exactly one and refuses a
  record that moved under it; the store is named by one environment variable
  or not at all.
- **The governor refuses without spending anything** — an ineligible role on
  the safe direction, a missing reason on every path, a default switch onto a
  running canary, and a write that keeps losing the race.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import fakeredis
import pytest
import redis
from intake_platform.admin import FourEyesService
from intake_platform.admin.actions import VOICE_CANARY_SET, VOICE_PROFILE_SWITCH
from intake_platform.admin.flag_governance import (
    ChangeReasonMissing,
    FlagChangeReason,
    build_flag_change_justification,
)
from intake_platform.admin.four_eyes import ActorBlock, Justification
from intake_platform.admin.roles import AdminRole
from intake_platform.admin.voice_governance import (
    VoiceCanaryIsDefault,
    VoiceControlChanged,
    VoiceControlGovernor,
    VoiceRoleIneligible,
)
from intake_platform.voice_control import (
    ENV_VOICE_CONTROL_REDIS_URL,
    KEY_PREFIX,
    CanaryWeightOutOfBounds,
    RedisVoiceControlStore,
    TenantInvalid,
    TenantVoiceControl,
    UnknownVoiceProfile,
    VoiceControlConflict,
    VoiceControlProfile,
    VoiceControlUnavailable,
    parse_canary_weight,
    parse_profile,
    voice_control_store_from_env,
)
from pydantic import ValidationError

TENANT = "tenant-g"
NOW = datetime(2026, 9, 27, 9, 0, tzinfo=UTC)
REASON = build_flag_change_justification(
    reason_class=FlagChangeReason.INCIDENT_MITIGATION,
    free_text="Speech lane degraded; typed until it recovers.",
)
BLANK = Justification(
    reason_class=FlagChangeReason.INCIDENT_MITIGATION,
    free_text="   ",
    controller_instruction_ref=None,
)


def _actor(role: AdminRole, n: int = 1) -> ActorBlock:
    return ActorBlock(
        subject=f"kc-sub-{role.value}-{n}",
        role=role,
        org="org:intake",
        authenticator_aaguid=f"aaguid-{n}",
        credential_id=f"cred-{role.value}-{n}",
        session_id=f"sid-{role.value}-{n}",
    )


def _store() -> RedisVoiceControlStore:
    return RedisVoiceControlStore(fakeredis.FakeRedis())


def _governor(store: Any = None) -> VoiceControlGovernor:
    return VoiceControlGovernor(
        FourEyesService(clock=lambda: NOW), store or _store(), clock=lambda: NOW
    )


# =====================================================================================
# the record
# =====================================================================================


class TestRecord:
    def _row(self, **fields: object) -> dict[str, object]:
        return {"tenant_id": TENANT, "revision": 1, **fields}

    def test_an_unconfigured_tenant_is_typed_with_no_canary(self) -> None:
        control = TenantVoiceControl.unconfigured(TENANT)
        assert control.configured is False
        assert control.effective_profile is VoiceControlProfile.TYPED
        assert control.canary_profile is None

    def test_the_kill_switch_decides_the_effective_profile(self) -> None:
        on_voice = TenantVoiceControl.model_validate(self._row(default_profile="residency_tr"))
        assert on_voice.effective_profile is VoiceControlProfile.RESIDENCY_TR
        killed = on_voice.model_copy(update={"kill_switch": True})
        assert killed.effective_profile is VoiceControlProfile.TYPED

    @pytest.mark.parametrize(
        "fields",
        [
            {"canary_weight": 10},  # a weight with no canary profile
            {"canary_weight": 10, "canary_profile": "typed"},  # a canary of the default
            {"canary_profile": "residency_tr"},  # a canary nobody can see
            {"canary_weight": 101, "canary_profile": "residency_tr"},
            {"canary_weight": True, "canary_profile": "residency_tr"},
            {"default_profile": "speech_to_speech"},
            {"changed_by": "Dr. Ayşe Yılmaz"},
            {"tenant_id": "Hastane A"},
            {"revision": -1},
            {"note": "anything"},
        ],
    )
    def test_an_impossible_record_is_not_constructible(self, fields: dict[str, object]) -> None:
        with pytest.raises(ValidationError) as raised:
            TenantVoiceControl.model_validate(self._row(**fields))
        # the error carries no input (files/08 §0c F12)
        assert "Ayşe" not in str(raised.value)
        assert "Hastane" not in str(raised.value)

    def test_a_coherent_canary_is(self) -> None:
        control = TenantVoiceControl.model_validate(
            self._row(canary_profile="residency_tr", canary_weight=25)
        )
        assert control.canary_weight == 25

    @pytest.mark.parametrize("value", [None, 1, "Typed", "typed ", b"typed"])
    def test_parse_profile_is_exact(self, value: object) -> None:
        with pytest.raises(UnknownVoiceProfile):
            parse_profile(value)

    @pytest.mark.parametrize("value", [True, False, -1, 101, 1.0, "1", None])
    def test_parse_canary_weight_is_an_integer_in_bounds(self, value: object) -> None:
        with pytest.raises(CanaryWeightOutOfBounds):
            parse_canary_weight(value)

    def test_parse_canary_weight_takes_the_bounds(self) -> None:
        assert (parse_canary_weight(0), parse_canary_weight(100)) == (0, 100)


# =====================================================================================
# the store
# =====================================================================================


class _WatchLosingPipeline:
    """A pipeline whose EXEC always loses the WATCH race."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def __enter__(self) -> _WatchLosingPipeline:
        self._inner.__enter__()
        return self

    def __exit__(self, *args: object) -> None:
        self._inner.__exit__(*args)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def execute(self) -> None:
        raise redis.WatchError("another writer")


class _RacingRedis(fakeredis.FakeRedis):
    def pipeline(self, *args: Any, **kwargs: Any) -> Any:  # type: ignore[override]
        return _WatchLosingPipeline(super().pipeline(*args, **kwargs))


class TestStore:
    def test_a_write_moves_the_revision_by_exactly_one(self) -> None:
        store = _store()
        with pytest.raises(ValueError, match="exactly one"):
            store.write(
                TenantVoiceControl.model_validate({"tenant_id": TENANT, "revision": 2}),
                expected_revision=0,
            )

    def test_a_write_over_a_record_that_moved_is_a_conflict(self) -> None:
        store = _store()
        first = TenantVoiceControl.model_validate({"tenant_id": TENANT, "revision": 1})
        store.write(first, expected_revision=0)
        with pytest.raises(VoiceControlConflict):
            store.write(first, expected_revision=0)

    def test_a_lost_watch_race_is_a_conflict(self) -> None:
        store = RedisVoiceControlStore(_RacingRedis())
        with pytest.raises(VoiceControlConflict):
            store.write(
                TenantVoiceControl.model_validate({"tenant_id": TENANT, "revision": 1}),
                expected_revision=0,
            )

    def test_an_unreachable_server_is_unavailable_on_every_operation(self) -> None:
        server = fakeredis.FakeServer()
        server.connected = False
        store = RedisVoiceControlStore(fakeredis.FakeRedis(server=server))
        for call in (
            lambda: store.read(TENANT),
            lambda: store.tenants(),
            lambda: store.write(
                TenantVoiceControl.model_validate({"tenant_id": TENANT, "revision": 1}),
                expected_revision=0,
            ),
        ):
            with pytest.raises(VoiceControlUnavailable) as raised:
                call()
            assert raised.value.code == "voice_control_unreachable"

    def test_a_record_filed_under_another_tenant_is_malformed(self) -> None:
        client = fakeredis.FakeRedis()
        store = RedisVoiceControlStore(client)
        client.set(
            store.key(TENANT),
            TenantVoiceControl.model_validate({"tenant_id": "tenant-h"}).model_dump_json(),
        )
        with pytest.raises(VoiceControlUnavailable) as raised:
            store.read(TENANT)
        assert raised.value.code == "voice_control_malformed"

    def test_a_key_that_is_not_a_tenant_id_makes_the_listing_malformed(self) -> None:
        client = fakeredis.FakeRedis()
        client.set(f"{KEY_PREFIX}Hastane A", b"{}")
        with pytest.raises(VoiceControlUnavailable) as raised:
            RedisVoiceControlStore(client).tenants()
        assert raised.value.code == "voice_control_malformed"

    def test_the_listing_is_every_configured_tenant_sorted(self) -> None:
        store = _store()
        for tenant in ("tenant-z", "tenant-b"):
            store.write(
                TenantVoiceControl.model_validate({"tenant_id": tenant, "revision": 1}),
                expected_revision=0,
            )
        assert [c.tenant_id for c in store.tenants()] == ["tenant-b", "tenant-z"]

    def test_a_key_is_refused_for_a_tenant_that_is_not_id_shaped(self) -> None:
        with pytest.raises(TenantInvalid):
            RedisVoiceControlStore.key("../tenant-b")

    def test_the_store_is_named_by_one_variable_or_not_at_all(self) -> None:
        assert voice_control_store_from_env({}) is None
        assert voice_control_store_from_env({ENV_VOICE_CONTROL_REDIS_URL: "  "}) is None
        with pytest.raises(ValueError, match="redis"):
            voice_control_store_from_env({ENV_VOICE_CONTROL_REDIS_URL: "http://redis:6379"})
        built = voice_control_store_from_env(
            {ENV_VOICE_CONTROL_REDIS_URL: "redis://127.0.0.1:6399/5"}
        )
        assert isinstance(built, RedisVoiceControlStore)


# =====================================================================================
# the governor
# =====================================================================================


class _AlwaysConflicting:
    def __init__(self) -> None:
        self.writes = 0

    def read(self, tenant_id: str) -> TenantVoiceControl:
        return TenantVoiceControl.unconfigured(tenant_id)

    def write(self, control: TenantVoiceControl, *, expected_revision: int) -> TenantVoiceControl:
        self.writes += 1
        raise VoiceControlConflict("always")

    def tenants(self) -> tuple[TenantVoiceControl, ...]:
        return ()


class TestGovernor:
    def test_a_role_outside_the_t1_set_cannot_pull_the_switch(self) -> None:
        with pytest.raises(VoiceRoleIneligible):
            _governor().engage_kill_switch(
                tenant_id=TENANT, actor=_actor(AdminRole.AUDITOR), justification=REASON
            )

    def test_the_safe_direction_retries_a_lost_race_and_then_says_so(self) -> None:
        store = _AlwaysConflicting()
        with pytest.raises(VoiceControlChanged):
            _governor(store).engage_kill_switch(
                tenant_id=TENANT, actor=_actor(AdminRole.SRE_ONCALL), justification=REASON
            )
        assert store.writes == 3

    @pytest.mark.parametrize("path", ["engage", "release", "profile", "canary"])
    def test_a_blank_reason_is_refused_on_every_path(self, path: str) -> None:
        governor = _governor()
        lead = _actor(AdminRole.CLINICAL_LEAD)
        calls = {
            "engage": lambda: governor.engage_kill_switch(
                tenant_id=TENANT, actor=lead, justification=BLANK
            ),
            "release": lambda: governor.open_kill_switch_release(
                tenant_id=TENANT, actor=lead, justification=BLANK
            ),
            "profile": lambda: governor.open_profile_switch(
                tenant_id=TENANT, profile="residency_tr", actor=lead, justification=BLANK
            ),
            "canary": lambda: governor.open_canary(
                tenant_id=TENANT,
                profile="residency_tr",
                weight=5,
                actor=lead,
                justification=BLANK,
            ),
        }
        with pytest.raises(ChangeReasonMissing):
            calls[path]()
        assert governor.pending() == ()

    def test_a_default_switch_onto_a_running_canary_is_refused(self) -> None:
        governor = _governor()
        lead, owner = _actor(AdminRole.CLINICAL_LEAD), _actor(AdminRole.QMS_OWNER, 2)
        pending = governor.open_canary(
            tenant_id=TENANT, profile="residency_tr", weight=20, actor=lead, justification=REASON
        )
        governor.approve(pending.id, action=VOICE_CANARY_SET, approver=owner, assertion_id="a-1")
        with pytest.raises(VoiceCanaryIsDefault):
            governor.open_profile_switch(
                tenant_id=TENANT, profile="residency_tr", actor=lead, justification=REASON
            )

    def test_a_canary_at_weight_zero_clears_the_canary(self) -> None:
        store = _store()
        governor = _governor(store)
        lead, owner = _actor(AdminRole.CLINICAL_LEAD), _actor(AdminRole.QMS_OWNER, 2)
        for weight, assertion in ((30, "a-1"), (0, "a-2")):
            pending = governor.open_canary(
                tenant_id=TENANT,
                profile="residency_tr",
                weight=weight,
                actor=lead,
                justification=REASON,
            )
            governor.approve(
                pending.id, action=VOICE_CANARY_SET, approver=owner, assertion_id=assertion
            )
        control = store.read(TENANT)
        assert (control.canary_profile, control.canary_weight) == (None, 0)
        assert control.revision == 2
        assert control.changed_by == lead.subject
        assert control.approved_by == owner.subject

    def test_an_approval_that_loses_the_write_race_is_refused(self) -> None:
        store = _store()
        four_eyes = FourEyesService(clock=lambda: NOW)
        governor = VoiceControlGovernor(four_eyes, store, clock=lambda: NOW)
        pending = governor.open_profile_switch(
            tenant_id=TENANT,
            profile="residency_tr",
            actor=_actor(AdminRole.CLINICAL_LEAD),
            justification=REASON,
        )
        racing = VoiceControlGovernor(
            four_eyes, RedisVoiceControlStore(_RacingRedis()), clock=lambda: NOW
        )
        with pytest.raises(VoiceControlChanged):
            racing.approve(
                pending.id,
                action=VOICE_PROFILE_SWITCH,
                approver=_actor(AdminRole.QMS_OWNER, 2),
                assertion_id="a-9",
            )

    def test_pending_lists_voice_ceremonies_only_and_drops_decided_ones(self) -> None:
        governor = _governor()
        lead, owner = _actor(AdminRole.CLINICAL_LEAD), _actor(AdminRole.QMS_OWNER, 2)
        first = governor.open_profile_switch(
            tenant_id=TENANT, profile="residency_tr", actor=lead, justification=REASON
        )
        assert [p.id for p in governor.pending()] == [first.id]
        governor.approve(first.id, action=VOICE_PROFILE_SWITCH, approver=owner, assertion_id="x")
        assert governor.pending() == ()
