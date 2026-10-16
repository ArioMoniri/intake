"""INT-515 — the RED trigger arrives over the data channel with the media track torn down.

Issue #877's third test, and CLAUDE.md invariant 21: *"The RED script is
pre-positioned on the device and triggered over the data channel — the RED
path touches no media transport."* files/03 §4.6 invariant 4 adds how it must
be proven: *"it must assert the RED path touches no media transport, not merely
that the deadline was met."*

INT-093 built the controller (``talker.red_path.RedPreemption``) against two
ports. This file drives the controller through the two adapters the deployment
binds to those ports (``intake_voice_runtime.sfu``):

- ``RoomMediaTeardown`` — the ``PlaybackCanceller``: it stops the agent's
  outbound audio at the SFU (mutes every audio track the agent publishes), after
  the in-process sink, so nothing more is forwarded to the patient;
- ``RoomRedChannel`` — the ``RedDataChannel``: one reliable data packet to the
  patient's identity, sent through the SFU's server API. The agent's own peer
  connection is never involved, which is why the agent's room token carries
  ``canPublishData: false`` and the RED still arrives.

The SFU is a stand-in speaking LiveKit's RoomService Twirp JSON API over
``httpx.MockTransport`` — no socket, no room, no vendor. It keeps a model of the
room (who publishes which track, which tracks are forwarded) and hands every
data packet to a stand-in device that decodes it the way
``apps/mobile/src/lib/livekit/red.ts`` ``decodeRedTrigger`` does.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from clinical_schemas.triage import RedLocation, RedRegister
from intake_platform.room_tokens import LiveKitCredentials, room_name
from intake_voice_runtime.sfu import (
    AGENT_IDENTITY,
    PATIENT_IDENTITY,
    RED_TOPIC,
    RoomMediaTeardown,
    RoomRedChannel,
    RoomServiceClient,
    RoomServiceError,
)
from intake_voice_runtime.talker.red_path import (
    RedPreemption,
    RedTriggerAck,
    RedTriggerMessage,
)
from prometheus_client import REGISTRY
from red_harness import MediaPlane, RecordingClinicNotifier
from talker_harness import FakeClock
from test_red_preemption import RULE_A, SCRIPTS, red_result

REPO = Path(__file__).resolve().parents[2]
CLIENT_RED = REPO / "apps" / "mobile" / "src" / "lib" / "livekit" / "red.ts"
SESSION = "5d2c1a0e-8b7f-4c3a-9e21-6f4b3a2c1d0e"
ROOM = room_name(SESSION)
CREDENTIALS = LiveKitCredentials(api_key="k" * 40, api_secret="s" * 64)
NOW = datetime(2026, 10, 16, 9, 0, tzinfo=UTC)
TWIRP = "/twirp/livekit.RoomService/"


def _client_id_shape() -> re.Pattern[str]:
    match = re.search(r"const ID_SHAPE = /(.+)/;", CLIENT_RED.read_text(encoding="utf-8"))
    assert match, "the client's ID_SHAPE moved"
    return re.compile(match.group(1))


def decode_red_trigger(payload: bytes) -> dict[str, str] | None:
    """``decodeRedTrigger`` in Python: everything not an unambiguous, fully
    specified RED trigger is refused, never coerced."""
    try:
        message = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    if not isinstance(message, dict) or message.get("kind") != "red_trigger":
        return None
    shape = _client_id_shape()
    for key in ("ruleId", "scriptId"):
        if not isinstance(message.get(key), str) or not shape.match(message[key]):
            return None
    if message.get("register") not in {r.value for r in RedRegister}:
        return None
    if message.get("location") not in {loc.value for loc in RedLocation}:
        return None
    return {key: message[key] for key in ("kind", "ruleId", "register", "location", "scriptId")}


# --- the stand-in SFU and device ---------------------------------------------------------


@dataclass
class Track:
    sid: str
    kind: str
    source: str
    forwarded: bool = True


@dataclass
class Device:
    """The patient's phone: a data-channel receiver with a pre-positioned pack."""

    clock: FakeClock
    triggers: list[dict[str, str]] = field(default_factory=list)
    started_at_ms: dict[str, float] = field(default_factory=dict)
    #: virtual ms from the packet landing to the first sample of the local script
    device_output_ms: float = 25.0

    def receive(self, payload: bytes, *, reliable: bool, topic: str) -> None:
        trigger = decode_red_trigger(payload)
        assert trigger is not None, "the device refused the packet"
        assert reliable, "a RED rides the reliable, ordered channel"
        assert topic == RED_TOPIC
        self.triggers.append(trigger)
        self.started_at_ms[trigger["scriptId"]] = self.clock.now_ms() + self.device_output_ms


@dataclass
class DeviceAcks:
    """``RedStartAcks``: the device's own stamp of when the script started."""

    device: Device
    clock: FakeClock

    async def started(self, message: RedTriggerMessage) -> RedTriggerAck:
        assert message.script_id in self.device.started_at_ms, "acked a trigger never delivered"
        at = self.device.started_at_ms[message.script_id]
        await self.clock.sleep(max(0.0, at - self.clock.now_ms()) / 1000.0)
        return RedTriggerAck(script_started_at_ms=at)


@dataclass
class Sfu:
    """LiveKit's RoomService over Twirp JSON, for one room."""

    device: Device
    participants: dict[str, list[Track]] = field(
        default_factory=lambda: {
            PATIENT_IDENTITY: [Track("TR_patient_mic", "AUDIO", "MICROPHONE")],
            AGENT_IDENTITY: [Track("TR_agent_voice", "AUDIO", "MICROPHONE")],
        }
    )
    calls: list[str] = field(default_factory=list)
    tokens: list[dict[str, Any]] = field(default_factory=list)
    unreachable: set[str] = field(default_factory=set)

    def _verify(self, request: httpx.Request) -> dict[str, Any]:
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        assert scheme == "Bearer"
        head, body, signature = token.split(".")
        expected = hmac.new(
            CREDENTIALS.api_secret.encode(), f"{head}.{body}".encode(), hashlib.sha256
        ).digest()
        assert base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4)) == expected
        claims: dict[str, Any] = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        self.tokens.append(claims)
        return claims

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/":
            return httpx.Response(200, text="OK")
        assert request.url.path.startswith(TWIRP), request.url.path
        method = request.url.path.removeprefix(TWIRP)
        self.calls.append(method)
        claims = self._verify(request)
        body = json.loads(request.content)
        if claims["video"] != {"room": body["room"], "roomAdmin": True}:
            return httpx.Response(401, json={"code": "unauthenticated"})
        if method in self.unreachable:
            return httpx.Response(503, json={"code": "unavailable", "msg": "sfu restarting"})
        if body["room"] != ROOM:
            return httpx.Response(404, json={"code": "not_found"})
        if method == "ListParticipants":
            return httpx.Response(
                200,
                json={
                    "participants": [
                        {
                            "identity": identity,
                            "tracks": [
                                {
                                    "sid": t.sid,
                                    "type": t.kind,
                                    "source": t.source,
                                    "muted": not t.forwarded,
                                }
                                for t in tracks
                            ],
                        }
                        for identity, tracks in self.participants.items()
                    ]
                },
            )
        if method == "MutePublishedTrack":
            for track in self.participants[body["identity"]]:
                if track.sid == body["track_sid"]:
                    track.forwarded = not body["muted"]
            return httpx.Response(200, json={"track": {"sid": body["track_sid"]}})
        if method == "SendData":
            assert body["kind"] == "RELIABLE"
            assert body["destination_identities"] == [PATIENT_IDENTITY]
            self.device.receive(base64.b64decode(body["data"]), reliable=True, topic=body["topic"])
            return httpx.Response(200, json={})
        return httpx.Response(404, json={"code": "bad_route"})

    def forwarded(self, identity: str) -> dict[str, bool]:
        return {track.sid: track.forwarded for track in self.participants[identity]}


class Rig:
    """The RED path wired to the deployment's adapters over the stand-in SFU."""

    def __init__(self, *, unreachable: set[str] | None = None) -> None:
        self.clock = FakeClock()
        self.device = Device(clock=self.clock)
        self.sfu = Sfu(device=self.device, unreachable=unreachable or set())
        self.rooms = RoomServiceClient(
            "http://livekit:7880",
            CREDENTIALS,
            now=lambda: NOW,
            transport=httpx.MockTransport(self.sfu.handle),
        )
        #: the agent's in-process audio sink: its record proves that nothing on
        #: the RED path plays, synthesises or fetches
        self.local = MediaPlane(clock=self.clock, cancel_cost_ms=2.0)
        self.clinic = RecordingClinicNotifier()
        self.path = RedPreemption(
            canceller=RoomMediaTeardown(self.rooms, SESSION, local=self.local),
            channel=RoomRedChannel(self.rooms, SESSION, acks=DeviceAcks(self.device, self.clock)),
            clinic=self.clinic,
            scripts=SCRIPTS,
            clock=self.clock,
        )

    def trigger(self, **kwargs: Any) -> Any:
        return self.clock.run(self.path.trigger(red_result(**kwargs), evaluated_at_ms=0.0))


# --- the trigger arrives over the data channel, the media track torn down ----------------


def test_the_red_trigger_arrives_over_the_data_channel_with_the_media_track_torn_down() -> None:
    rig = Rig()
    outcome = rig.trigger(register=RedRegister.ALERT, location=RedLocation.REMOTE)

    # the media track is torn down: the SFU forwards nothing more of the agent
    assert rig.sfu.forwarded(AGENT_IDENTITY) == {"TR_agent_voice": False}
    # …and only the agent's: the patient's microphone is not the server's to touch
    assert rig.sfu.forwarded(PATIENT_IDENTITY) == {"TR_patient_mic": True}
    # the trigger arrived on the device over the data channel, ids and axes only
    assert rig.device.triggers == [
        {
            "kind": "red_trigger",
            "ruleId": RULE_A,
            "register": "ALERT",
            "location": "REMOTE",
            "scriptId": "sentetik.a.remote",
        }
    ]
    # the teardown ran before the trigger was sent
    assert rig.sfu.calls == ["ListParticipants", "MutePublishedTrack", "SendData"]
    assert outcome.media_plane_unreachable is False
    assert outcome.violations == ()
    assert outcome.script_started_at_ms is not None
    assert rig.clinic.notifications[0].rule_ids == (RULE_A,)


def test_the_red_path_touches_no_media_transport() -> None:
    """files/03 §4.6 invariant 4's own test: the in-process sink saw a cancel
    and nothing else, and the one call the data channel made is SendData."""
    rig = Rig()
    rig.trigger()
    assert rig.local.calls == ["cancel"]
    assert rig.local.played == []
    channel_calls = rig.sfu.calls[rig.sfu.calls.index("SendData") :]
    assert channel_calls == ["SendData"]


def test_with_the_media_plane_gone_the_trigger_still_arrives() -> None:
    """Invariant 21's reason for the design: a RED renders with the media
    track gone and only the data channel alive."""
    rig = Rig(unreachable={"ListParticipants", "MutePublishedTrack"})
    outcome = rig.trigger()
    assert outcome.media_plane_unreachable is True
    assert [t["scriptId"] for t in rig.device.triggers] == ["sentetik.a.remote"]
    assert rig.clinic.notifications, "the clinic hears of it whatever the media plane did"


def test_an_agent_with_nothing_published_has_nothing_to_tear_down() -> None:
    rig = Rig()
    rig.sfu.participants[AGENT_IDENTITY] = []
    outcome = rig.trigger()
    assert rig.sfu.calls == ["ListParticipants", "SendData"]
    assert outcome.media_plane_unreachable is False


def test_a_deferred_clinician_red_changes_nothing_the_patient_sees_or_hears() -> None:
    """files/02 §5.3: patient screen unchanged; the finding routes to the clinician."""
    rig = Rig()
    outcome = rig.trigger(register=RedRegister.DEFERRED_CLINICIAN)
    assert rig.sfu.calls == []
    assert rig.device.triggers == []
    assert rig.sfu.forwarded(AGENT_IDENTITY) == {"TR_agent_voice": True}
    assert outcome.notified_clinician is True


@pytest.mark.parametrize("location", list(RedLocation))
def test_every_location_reaches_the_device_with_its_own_script(location: RedLocation) -> None:
    rig = Rig()
    rig.trigger(register=RedRegister.CALM, location=location)
    assert rig.device.triggers[0]["location"] == location.value
    assert rig.device.triggers[0]["scriptId"] == SCRIPTS.script_id_for(RULE_A, location)


def test_a_data_channel_failure_is_raised_and_counted_not_swallowed() -> None:
    rig = Rig(unreachable={"SendData"})
    before = _sends("failed")
    with pytest.raises(RoomServiceError) as raised:
        rig.trigger()
    assert raised.value.status == 503
    # the error names the status, never the SFU's body
    assert "sfu restarting" not in str(raised.value)
    assert _sends("failed") == before + 1
    # the clinician route ran first and is not undone by a transport failure
    assert rig.clinic.notifications


def _sends(outcome: str) -> float:
    return REGISTRY.get_sample_value("voice_red_data_channel_total", {"outcome": outcome}) or 0.0


def test_a_sent_trigger_is_counted() -> None:
    before = _sends("sent")
    Rig().trigger()
    assert _sends("sent") == before + 1


# --- the server-API credential ------------------------------------------------------------


def test_every_server_call_carries_a_one_room_admin_token_that_lives_a_minute() -> None:
    rig = Rig()
    rig.trigger()
    assert rig.sfu.tokens
    for claims in rig.sfu.tokens:
        assert claims["video"] == {"room": ROOM, "roomAdmin": True}
        assert claims["iss"] == CREDENTIALS.api_key
        assert 0 < claims["exp"] - claims["iat"] <= 60
        # no grant beyond the one room: no roomCreate, roomList, roomRecord,
        # ingressAdmin, recorder or agent
        assert set(claims["video"]) == {"room", "roomAdmin"}


def test_another_sessions_room_is_never_addressed() -> None:
    rig = Rig()
    other = "9e8d7c6b-5a49-4c38-8b27-16a5f4e3d2c1"
    rogue = RoomRedChannel(rig.rooms, other, acks=DeviceAcks(rig.device, rig.clock))
    message = RedTriggerMessage(
        rule_id=RULE_A, register=RedRegister.ALERT, location=RedLocation.REMOTE, script_id="x.y"
    )
    with pytest.raises(RoomServiceError) as raised:
        rig.clock.run(rogue.publish(message))
    assert raised.value.status == 404
    assert rig.device.triggers == []
    assert rig.sfu.tokens[-1]["video"]["room"] == room_name(other)


def test_the_room_service_rejects_a_free_text_session_id() -> None:
    rig = Rig()
    with pytest.raises(ValueError):
        rig.clock.run(rig.rooms.list_participants("Ayşe Yılmaz"))
    assert rig.sfu.calls == []


def test_an_uppercase_session_id_is_not_canonical() -> None:
    rig = Rig()
    with pytest.raises(ValueError):
        rig.clock.run(rig.rooms.list_participants(SESSION.upper()))
    assert rig.sfu.calls == []


def test_a_malformed_participant_list_reads_as_nothing_published() -> None:
    def odd(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"participants": ["agent", {"identity": "agent"}]})

    rooms = RoomServiceClient(
        "http://livekit:7880", CREDENTIALS, now=lambda: NOW, transport=httpx.MockTransport(odd)
    )
    clock = FakeClock()
    participants = clock.run(rooms.list_participants(SESSION))
    assert [(p.identity, p.tracks) for p in participants] == [("agent", ())]
    clock.run(rooms.aclose())


def test_a_failing_local_sink_still_tears_down_at_the_sfu_and_is_reported() -> None:
    rig = Rig()
    rig.local.cancel_raises = RuntimeError("sink gone")
    outcome = rig.trigger()
    assert outcome.media_plane_unreachable is True
    assert rig.sfu.forwarded(AGENT_IDENTITY) == {"TR_agent_voice": False}
    assert [t["scriptId"] for t in rig.device.triggers] == ["sentetik.a.remote"]


def test_an_already_muted_agent_track_is_left_alone() -> None:
    rig = Rig()
    rig.sfu.participants[AGENT_IDENTITY][0].forwarded = False
    rig.trigger()
    assert "MutePublishedTrack" not in rig.sfu.calls


def test_the_sfu_ping_reads_its_liveness() -> None:
    rig = Rig()
    assert rig.clock.run(rig.rooms.ping()) is True

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    dead = RoomServiceClient(
        "http://livekit:7880", CREDENTIALS, now=lambda: NOW, transport=httpx.MockTransport(down)
    )
    assert rig.clock.run(dead.ping()) is False


def test_the_payload_is_the_wire_shape_the_client_decodes_and_nothing_more() -> None:
    message = RedTriggerMessage(
        rule_id=RULE_A,
        register=RedRegister.SILENT,
        location=RedLocation.ON_SITE,
        script_id="sentetik.a.on_site",
    )
    wire: Mapping[str, Any] = json.loads(message.model_dump_json(by_alias=True))
    assert set(wire) == {"kind", "ruleId", "register", "location", "scriptId"}
    assert decode_red_trigger(message.model_dump_json(by_alias=True).encode()) == dict(wire)
