"""INT-515 — the room-token route behind the patient's DPoP session.

Issue #877: *"Give it a token route behind the patient's DPoP session."* The
client contract was written first (INT-103, ``apps/mobile/src/lib/livekit/
token.ts``): ``POST /v1/visits/{sessionId}/voice-token`` answers ``{url, token,
room, expires_at_ms}``, the url is ``wss://``, the room is ``intake-<session
uuid>`` and anything else is refused by the client. ``mint_room_token``
(INT-090) is the only minter and its grant is pinned in
``tests/voice/test_room_tokens.py``; this file pins the door in front of it:

- only the patient's own visit, and only on the OTP/DPoP tier — the dev bearer
  tier never opens a media room (it is absent outside dev anyway, INT-325);
- the visit's ``core`` consent is checked like every other visit route;
- unconfigured is 503, never a token for a guessed SFU;
- ids only: the request carries the visit id in the path and nothing else, the
  response names the room by id, the audit row names the visit by id, and the
  metric carries an outcome.
"""

from __future__ import annotations

import base64
import json
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from api_harness import ADMIN_TOKEN, PATIENT_TOKEN, ApiHarness, build_harness
from fastapi import Request
from intake_api.auth import AUTH_TIER_OTP, require_principal
from intake_api.dev_fixture import ADMIN_ACCOUNT, PATIENT_ACCOUNT, DevAccount
from intake_api.voice_token import VoiceRooms, voice_rooms_from_env
from intake_platform.room_tokens import TOKEN_TTL_S, LiveKitCredentials
from prometheus_client import REGISTRY

ROOMS = VoiceRooms(
    public_url="wss://rtc.203-0-113-7.sslip.io",
    credentials=LiveKitCredentials(api_key="k" * 64, api_secret="s" * 64),
    clock=lambda: datetime(2026, 10, 16, 9, 0, tzinfo=UTC),
)

VISIT_BODY = {
    "hospital": "Ankara Şehir Hastanesi",
    "department": "İç Hastalıkları",
    "date": "2026-11-03",
}


@pytest.fixture()
def voice(tmp_path: Path) -> Iterator[ApiHarness]:
    yield from build_harness(
        tmp_path, token_patient=PATIENT_TOKEN, token_admin=ADMIN_TOKEN, voice_rooms=ROOMS
    )


@pytest.fixture()
def unwired(tmp_path: Path) -> Iterator[ApiHarness]:
    yield from build_harness(tmp_path, token_patient=PATIENT_TOKEN, token_admin=ADMIN_TOKEN)


def _as_dpop(harness: ApiHarness, account: DevAccount = PATIENT_ACCOUNT) -> None:
    """The DPoP tier as ``require_principal`` resolves it (INT-131's own suite
    proves the proof check): the account, with the request tagged ``otp``."""

    async def principal(request: Request) -> DevAccount:
        request.state.auth_tier = AUTH_TIER_OTP
        return account

    harness.client.app.dependency_overrides[require_principal] = principal  # type: ignore[attr-defined]


def _visit(harness: ApiHarness) -> str:
    response = harness.client.post("/v1/visits", json=VISIT_BODY, headers=harness.patient())
    assert response.status_code == 201
    return str(response.json()["id"])


def _token(harness: ApiHarness, visit_id: str) -> Any:
    return harness.client.post(f"/v1/visits/{visit_id}/voice-token", headers=harness.patient())


def _claims(token: str) -> dict[str, Any]:
    payload = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))


def _issued(outcome: str) -> float:
    return REGISTRY.get_sample_value("voice_room_tokens_total", {"outcome": outcome}) or 0.0


def test_the_patient_gets_their_own_rooms_token_in_the_client_contract_shape(
    voice: ApiHarness,
) -> None:
    visit_id = _visit(voice)
    _as_dpop(voice)
    response = _token(voice, visit_id)
    assert response.status_code == 200, response.text
    body = response.json()
    # exactly what apps/mobile/src/lib/livekit/token.ts parseTokenResponse reads
    assert set(body) == {"url", "token", "room", "expires_at_ms"}
    assert body["url"] == "wss://rtc.203-0-113-7.sslip.io"
    assert body["room"] == f"intake-{visit_id}"
    claims = _claims(body["token"])
    assert claims["sub"] == "patient"
    assert claims["video"]["room"] == f"intake-{visit_id}"
    assert claims["video"]["canPublishData"] is False
    assert claims["video"]["canPublishSources"] == ["microphone"]
    assert body["expires_at_ms"] == claims["exp"] * 1000
    assert claims["exp"] - claims["iat"] == TOKEN_TTL_S
    assert response.headers["cache-control"] == "no-store"


def test_the_dev_bearer_tier_never_opens_a_media_room(voice: ApiHarness) -> None:
    visit_id = _visit(voice)
    response = _token(voice, visit_id)
    assert response.status_code == 403
    assert response.json() == {"error": "voice_requires_dpop"}


def test_another_patients_visit_is_not_found(voice: ApiHarness) -> None:
    _as_dpop(voice)
    response = _token(voice, str(uuid.uuid4()))
    assert response.status_code == 404
    assert response.json() == {"error": "not_found"}


def test_a_clinic_account_cannot_join_a_patients_room(voice: ApiHarness) -> None:
    visit_id = _visit(voice)
    _as_dpop(voice, ADMIN_ACCOUNT)
    response = _token(voice, visit_id)
    assert response.status_code == 403
    assert response.json() == {"error": "forbidden"}


def test_a_revoked_core_consent_refuses_the_room(voice: ApiHarness) -> None:
    visit_id = _visit(voice)
    voice.revoke_consent("core")
    _as_dpop(voice)
    response = _token(voice, visit_id)
    assert response.status_code == 403
    assert response.json()["error"] == "consent_required"


def test_unconfigured_is_503_never_a_token_for_a_guessed_sfu(unwired: ApiHarness) -> None:
    visit_id = _visit(unwired)
    _as_dpop(unwired)
    response = _token(unwired, visit_id)
    assert response.status_code == 503
    assert response.json() == {"error": "voice_room_unconfigured"}


def test_a_non_uuid_visit_id_is_refused_before_anything_is_minted(voice: ApiHarness) -> None:
    _as_dpop(voice)
    response = voice.client.post("/v1/visits/Ayşe/voice-token", headers=voice.patient())
    assert response.status_code == 422


def test_each_issue_is_audited_by_id_and_counted(voice: ApiHarness) -> None:
    visit_id = _visit(voice)
    _as_dpop(voice)
    before = _issued("issued")
    assert _token(voice, visit_id).status_code == 200
    assert _issued("issued") == before + 1

    rows = [e for e in voice.audit_store.entries() if e.action == "api.voice.token.issue"]
    assert [row.resource_ref for row in rows] == [f"visit:{visit_id}"]
    # ids only: never the token, never a credential, never a name
    assert [row.actor for row in rows] == [PATIENT_ACCOUNT.account_id]


def test_a_refusal_is_counted_by_reason(voice: ApiHarness) -> None:
    visit_id = _visit(voice)
    before = _issued("requires_dpop")
    _token(voice, visit_id)
    assert _issued("requires_dpop") == before + 1


# --- the deployment's environment ------------------------------------------------------


def test_the_environment_builds_the_rooms_only_when_every_fact_is_present() -> None:
    env = {
        "INTAKE_LIVEKIT_PUBLIC_URL": "wss://rtc.203-0-113-7.sslip.io",
        "LIVEKIT_API_KEY": "k" * 64,
        "LIVEKIT_API_SECRET": "s" * 64,
    }
    rooms = voice_rooms_from_env(env)
    assert rooms is not None and rooms.public_url == env["INTAKE_LIVEKIT_PUBLIC_URL"]
    for missing in env:
        assert voice_rooms_from_env({k: v for k, v in env.items() if k != missing}) is None


@pytest.mark.parametrize(
    "url",
    ["ws://rtc.example.test", "https://rtc.example.test", "wss://", "wss://rtc.example.test/x?y=1"],
)
def test_only_a_bare_wss_origin_is_a_signalling_url(url: str) -> None:
    env = {
        "INTAKE_LIVEKIT_PUBLIC_URL": url,
        "LIVEKIT_API_KEY": "k" * 64,
        "LIVEKIT_API_SECRET": "s" * 64,
    }
    assert voice_rooms_from_env(env) is None


def test_the_route_reads_no_body_and_echoes_no_input(voice: ApiHarness) -> None:
    visit_id = _visit(voice)
    _as_dpop(voice)
    response = voice.client.post(
        f"/v1/visits/{visit_id}/voice-token",
        headers=voice.patient(),
        json={"room": "intake-someone-else", "identity": "agent"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["room"] == f"intake-{visit_id}"
    assert _claims(body["token"])["sub"] == "patient"
