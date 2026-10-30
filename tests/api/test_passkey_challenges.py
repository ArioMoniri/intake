"""INT-582 — passkey challenges and step-up grants are single-use, short-lived
and bound to the patient, the device session, the ceremony and the action.

A challenge spent once is gone whatever the outcome; a mismatched binding
burns it too, so a probe cannot keep a challenge alive by trying it against
the wrong action first. Near misses: the same binding inside the window
passes, and a second challenge for the same binding is independent.
fakeredis and an injected clock (docs/TDD.md rule 6) — nothing sleeps.
"""

from __future__ import annotations

import uuid
from dataclasses import replace

import fakeredis
import pytest
from intake_api.passkey.challenges import (
    CHALLENGE_TTL_S,
    GRANT_TTL_S,
    Binding,
    Ceremony,
    ChallengeStore,
    Spent,
)

TENANT = uuid.UUID("00000000-0000-4000-8000-0000000000a1")
PATIENT = uuid.UUID("00000000-0000-4000-8000-0000000000b2")


class Clock:
    def __init__(self) -> None:
        self.now = 1_800_000_000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture()
def clock() -> Clock:
    return Clock()


@pytest.fixture()
def redis_client() -> fakeredis.FakeStrictRedis:
    return fakeredis.FakeStrictRedis()


@pytest.fixture()
def store(redis_client: fakeredis.FakeStrictRedis, clock: Clock) -> ChallengeStore:
    return ChallengeStore(redis_client, now_fn=clock)


STEP_UP = Binding(
    tenant_id=TENANT,
    patient_id=PATIENT,
    session_ref="jkt-device-a",
    ceremony=Ceremony.STEP_UP,
    action="data_export",
)


def test_a_challenge_is_32_random_bytes_and_spends_once(store: ChallengeStore) -> None:
    challenge = store.issue(STEP_UP)
    assert len(challenge) == 32
    assert store.consume(challenge, STEP_UP) is Spent.OK
    assert store.consume(challenge, STEP_UP) is Spent.MISSING  # the replay


def test_two_challenges_for_one_binding_are_independent(store: ChallengeStore) -> None:
    first, second = store.issue(STEP_UP), store.issue(STEP_UP)
    assert first != second
    assert store.consume(second, STEP_UP) is Spent.OK
    assert store.consume(first, STEP_UP) is Spent.OK


@pytest.mark.parametrize(
    "other",
    [
        replace(STEP_UP, action="data_delete"),  # a challenge for another action
        replace(STEP_UP, session_ref="jkt-device-b"),  # another device session
        replace(STEP_UP, patient_id=uuid.uuid4()),  # another patient
        replace(STEP_UP, tenant_id=uuid.uuid4()),  # another tenant
        replace(STEP_UP, ceremony=Ceremony.REGISTER, action=None),  # another ceremony
    ],
)
def test_a_challenge_spent_under_another_binding_is_refused_and_burnt(
    store: ChallengeStore, other: Binding
) -> None:
    challenge = store.issue(STEP_UP)
    assert store.consume(challenge, other) is Spent.MISMATCH
    # burnt: the right binding cannot use it afterwards either
    assert store.consume(challenge, STEP_UP) is Spent.MISSING


def test_a_challenge_expires_after_its_window(store: ChallengeStore, clock: Clock) -> None:
    challenge = store.issue(STEP_UP)
    clock.now += CHALLENGE_TTL_S + 1
    assert store.consume(challenge, STEP_UP) is Spent.EXPIRED


def test_near_miss_a_challenge_inside_its_window_spends(
    store: ChallengeStore, clock: Clock
) -> None:
    challenge = store.issue(STEP_UP)
    clock.now += CHALLENGE_TTL_S - 1
    assert store.consume(challenge, STEP_UP) is Spent.OK


def test_an_unknown_challenge_is_missing(store: ChallengeStore) -> None:
    assert store.consume(b"\x00" * 32, STEP_UP) is Spent.MISSING


def test_a_grant_spends_once_for_its_own_action(store: ChallengeStore) -> None:
    grant = store.issue_grant(STEP_UP)
    assert store.consume_grant(grant, replace(STEP_UP, action="doctor_link_issue")) is (
        Spent.MISMATCH
    )
    assert store.consume_grant(grant, STEP_UP) is Spent.MISSING  # burnt by the mismatch
    fresh = store.issue_grant(STEP_UP)
    assert store.consume_grant(fresh, STEP_UP) is Spent.OK
    assert store.consume_grant(fresh, STEP_UP) is Spent.MISSING


def test_a_grant_expires(store: ChallengeStore, clock: Clock) -> None:
    grant = store.issue_grant(STEP_UP)
    clock.now += GRANT_TTL_S + 1
    assert store.consume_grant(grant, STEP_UP) is Spent.EXPIRED


def test_a_grant_is_not_a_challenge_and_a_challenge_is_not_a_grant(store: ChallengeStore) -> None:
    challenge = store.issue(STEP_UP)
    grant = store.issue_grant(STEP_UP)
    assert store.consume_grant(challenge.hex(), STEP_UP) is Spent.MISSING
    assert store.consume(grant.encode("ascii"), STEP_UP) is Spent.MISSING


def test_a_grant_from_a_registration_binding_is_refused(store: ChallengeStore) -> None:
    register = replace(STEP_UP, ceremony=Ceremony.REGISTER, action=None)
    with pytest.raises(ValueError, match="step-up"):
        store.issue_grant(register)


def test_nothing_secret_is_stored_in_the_clear(
    store: ChallengeStore, redis_client: fakeredis.FakeStrictRedis
) -> None:
    challenge = store.issue(STEP_UP)
    grant = store.issue_grant(STEP_UP)
    blob = b"".join(
        key + (redis_client.get(key) or b"") for key in redis_client.scan_iter(match="*")
    )
    assert challenge not in blob
    assert challenge.hex().encode() not in blob
    assert grant.encode("ascii") not in blob
