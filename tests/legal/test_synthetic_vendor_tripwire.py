"""INT-529 — the tripwire on the synthetic texts' "no outside party" sentences.

Three synthetic texts say that the patient's audio, answers and documents reach
no outside company. Each sentence is true only while nothing on the synthetic
host can send that data to a vendor. Two routes could make them false:

- **A PHI-path egress row.** The one admitted purpose is ``sms_otp_delivery``:
  INT-528's Netgsm row, live on the synthetic host since PR #905. It carries
  the sign-in number and the one-time code, never audio, answers or documents.
  The core text, the only one of the four that speaks of the account and the
  phone number, names that processor by its legal entity and country and says
  what reaches it. The other three texts carry no sign-in data and do not
  name it (``SMS_PROCESSOR_TEXTS``).
- **A hosted model lane that a deployed process sends patient data through.**
  ADR-035 lists the hosted vendors' rows (``openai-api``, ``elevenlabs-api``;
  INT-442). A row alone moves no patient data. The question is which code on
  the host can hand data to a hosted backend.

What the texts were verified against (28 Oct 2026; ``hosted_reach`` reads
each from the tree):
- **Compose.** The services; who sits on each network that leads off the host
  (``public``: caddy; ``vendor``: egress-proxy; ``sms-wan``: sms-egress); who
  shares each of the api's networks with it (``outbound``: the hosted-lane
  proxy alone; ``sms-out``: the SMS-only proxy alone, ADR-042); the api's
  command, which is the image's uvicorn; and every other service that runs
  the api's image, with its command. Today that is ``probes`` (INT-560,
  #950): synthetic infrastructure probes on ``backend`` and ``edge`` only,
  both internal, so it has no way off the host. It reaches postgres as
  ``svc_probe`` (no table grant), redis as ``intake-probe`` (PING only) and
  health endpoints, so no patient data crosses it. Its import closure is
  pinned like the API's.
- **Dispatchers.** ``model_lanes.dispatch`` has three importers, in
  voice-clips and voice-runtime. None is deployed or imported by the API.
- **Hosted-backend call sites.** The API holds the hosted backends
  (``model_lanes_from_env`` → ``router.hosted.backends``). Its one use is the
  console's identity probe (``model_lanes_console.py``). The only
  ``chat_json`` / ``transcribe`` / ``speech`` users are the three dispatchers,
  plus the self-hosted ``HttpTranscriber`` in ``scripts/voice/live_smoke.py``.
- **Routed references.** Two string literals name a gateway package: the
  hosted-lanes plugin name in ``model_lanes/wiring.py`` (the console's
  backends) and the clip lane in ``hosted_clip_lane.py``.
- **The clip lane.** It is reached only from ``hosted_clip_lane.py``, which
  passes the scripted-catalogue predicate, so only server-verified scripted
  text goes to ElevenLabs.
- **The API's import closure.** Taken transitively over first-party modules,
  it reaches no gateway module.

The hosted half fires when a hosted row is listed **and** any of those facts
moves. That covers a one-line ``router.hosted.backends[p].chat_json(...)`` in
the API, an ``importlib`` literal naming a gateway, a gateway reached
through another module, and a service that joins a network the api is on or
one that leads off the host.

When it fires, the fix is not to widen the verified sets. The texts must
first name each recipient by its verified legal entity and country (files/06
§2.1's consent/vendor parity). Then the synthetic index is re-signed and every
grant is re-prompted. Only then may a set move. INT-515 (voice-runtime and an
SFU on this host, GitHub #877) is the planned change that fires it.

Narrowed from "any listed hosted row" on the INT-529 refresh, 16 Oct 2026.
Widened again after the legal re-verification found the backend bypass.
Re-cut on 28 Oct 2026 for the SMS proxy (sms-egress), after the core text
named Netgsm. The legal-reviewer verifies it (docs/evidence/INT-529.md §12,
§13).
"""

from __future__ import annotations

import ast
import string
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path

import pytest
import yaml
from hosted_reach import (
    api_reach,
    compose_facts,
    dispatchers,
    gateway_modules,
    hosted_call_sites,
    import_graph,
    python_sources,
    routed_references,
    service_reach,
)
from intake_api.otp_netgsm import SMS_TEMPLATE, NetgsmOtpRequest
from intake_platform.egress import DEDICATED_PERSONAL_PROXIES, EgressPurpose
from intake_platform.legal.synthetic import SYNTHETIC_LEGAL_ROOT, SyntheticLegalIndex
from intake_platform.model_lanes.model import TenantDataClass

REPO = Path(__file__).resolve().parents[2]

#: The sentences that are true only while no outside party receives the data.
NO_VENDOR_SENTENCES = {
    "acik_riza.voice": "Sesiniz hiçbir dış şirkete gönderilmez.",
    "acik_riza.core": "yalnızca hizmeti çalıştıran sistemlerimizde işlenir.",
    "acik_riza.documents": "yalnızca hizmeti çalıştıran sistemlerimizde işlenir.",
}
#: The PHI-path purpose these sentences do not cover (see the module docstring).
PHI_PATH_PURPOSES_OUTSIDE_THE_TEXTS = frozenset({"sms_otp_delivery"})

#: The sign-in SMS processor, as its own aydınlatma names it
#: (docs/legal/sources/netgsm-aydinlatma/, retrieved 28 Oct 2026), and the one
#: text that names it. The other three carry no sign-in data, so they do not.
SMS_PROCESSOR = "Netgsm İletişim ve Bilgi Teknolojileri Anonim Şirketi"
SMS_PROCESSOR_COUNTRY = "Türkiye'de kuruludur"
SMS_PROCESSOR_TEXTS = {
    "acik_riza.core": True,
    "acik_riza.voice": False,
    "acik_riza.lane.affect": False,
    "acik_riza.documents": False,
}
SMS_HOST = "api.netgsm.com.tr"

_CONSOLE = "services/api/src/intake_api/admin/model_lanes_console.py"
_CLIP_LANE = "services/api/src/intake_api/hosted_clip_lane.py"
_VOICE_CLIPS_LANES = "packages/voice-clips/src/voice_clips/lanes.py"
_ADAPTER_LANES = "services/voice-runtime/src/intake_voice_runtime/adapters/lanes.py"
_EXTRACTION_LANES = "services/voice-runtime/src/intake_voice_runtime/extraction/lanes.py"


@dataclass(frozen=True)
class Reach:
    """Every fact the no-vendor sentences rest on, as the tree has it."""

    services: frozenset[str]
    #: network that leads off the host → its members
    external: Mapping[str, frozenset[str]]
    #: each network the api sits on → who shares it with the api
    api_peers: Mapping[str, frozenset[str]]
    api_command: object
    #: other services that run the api's own image -> their (command, entrypoint)
    image_commands: Mapping[str, tuple[object, object]]
    dispatchers: frozenset[str]
    call_sites: frozenset[tuple[str, str]]
    routed_refs: frozenset[tuple[str, str]]
    api_reach: frozenset[str]
    #: gateway modules the probes service's import closure reaches
    probes_reach: frozenset[str]


VERIFIED = Reach(
    services=frozenset(
        {
            "api",
            "postgres",
            "redis",
            "openbao",
            "minio",
            "keycloak",
            "oauth2-proxy",
            "admin-web",
            "egress-proxy",
            "sms-egress",
            # INT-560 (#950): synthetic probes only; see the backend/edge note below
            "probes",
            "caddy",
        }
    ),
    external={
        "public": frozenset({"caddy"}),
        "vendor": frozenset({"egress-proxy"}),
        "sms-wan": frozenset({"sms-egress"}),
    },
    api_peers={
        # probes (INT-560, #950) sits on backend and edge only, both internal, so
        # it has no way off the host. It runs the api image as
        # `intake_probes.app` and reaches postgres as svc_probe (LOGIN, CONNECT,
        # SELECT 1; no table grant), redis as intake-probe (PING only), and
        # health and readiness endpoints. No patient data crosses it, and its
        # import closure reaches no gateway (pinned below).
        "backend": frozenset({"postgres", "redis", "openbao", "minio", "keycloak", "probes"}),
        "edge": frozenset({"keycloak", "oauth2-proxy", "admin-web", "caddy", "probes"}),
        "outbound": frozenset({"egress-proxy"}),
        "sms-out": frozenset({"sms-egress"}),
    },
    api_command=(
        None,
        None,
        'CMD ["uvicorn", "intake_api.app:create_app", "--factory", "--host", "0.0.0.0", '
        '"--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*", "--no-server-header"]',
    ),
    image_commands={
        "probes": (
            (
                "uvicorn",
                "intake_probes.app:create_app",
                "--factory",
                "--host",
                "0.0.0.0",  # noqa: S104 - the compose command pinned verbatim; nothing binds here
                "--port",
                "8000",
                "--no-server-header",
            ),
            None,
        ),
    },
    dispatchers=frozenset({_VOICE_CLIPS_LANES, _ADAPTER_LANES, _EXTRACTION_LANES}),
    call_sites=frozenset(
        {
            (_CONSOLE, "hosted.backends"),
            (_VOICE_CLIPS_LANES, "HostedBackend"),
            (_VOICE_CLIPS_LANES, "speech"),
            (_ADAPTER_LANES, "HostedBackend"),
            (_ADAPTER_LANES, "transcribe"),
            (_EXTRACTION_LANES, "HostedBackend"),
            (_EXTRACTION_LANES, "chat_json"),
            ("scripts/voice/live_smoke.py", "transcribe"),
        }
    ),
    routed_refs=frozenset(
        {
            (
                "packages/intake_platform/src/intake_platform/model_lanes/wiring.py",
                "intake_hosted_lanes",
            ),
            (_CLIP_LANE, "intake_hosted_lanes.clip_lane"),
        }
    ),
    api_reach=frozenset(),
    probes_reach=frozenset(),
)


def _allowlist() -> dict[str, object]:
    loaded: dict[str, object] = yaml.safe_load(
        (REPO / "infra" / "security" / "egress-allowlist.yaml").read_text(encoding="utf-8")
    )
    return loaded


def _reach(sources: Mapping[str, str] | None = None) -> Reach:
    sources = python_sources() if sources is None else sources
    facts = compose_facts()
    found = dispatchers(sources)
    graph = import_graph(sources)
    return Reach(
        services=frozenset(facts["services"]),  # type: ignore[arg-type]
        external=dict(facts["external"]),  # type: ignore[call-overload]
        api_peers=dict(facts["api_peers"]),  # type: ignore[call-overload]
        api_command=facts["api_command"],
        image_commands=dict(facts["image_commands"]),  # type: ignore[call-overload]
        dispatchers=found,
        call_sites=hosted_call_sites(sources),
        routed_refs=routed_references(sources),
        api_reach=api_reach(graph, gateway_modules(found)),
        probes_reach=service_reach(graph, gateway_modules(found), "intake_probes"),
    )


def _new_members(
    now: Mapping[str, frozenset[str]], then: Mapping[str, frozenset[str]]
) -> list[tuple[str, str]]:
    return sorted(
        (network, member)
        for network, members in now.items()
        for member in members - then.get(network, frozenset())
    )


def _paths(reach: Reach) -> list[str]:
    """Every way ``reach`` differs from what the texts were verified against."""
    paths = [
        *(f"service {s!r}" for s in sorted(reach.services - VERIFIED.services)),
        *(
            f"{m!r} can leave the host on network {n!r}"
            for n, m in _new_members(reach.external, VERIFIED.external)
        ),
        *(
            f"the api shares network {n!r} with {m!r}"
            for n, m in _new_members(reach.api_peers, VERIFIED.api_peers)
        ),
        *(f"{p} imports dispatch" for p in sorted(reach.dispatchers - VERIFIED.dispatchers)),
        *(f"{p}: {what}" for p, what in sorted(reach.call_sites - VERIFIED.call_sites)),
        *(f"{p} names {v!r}" for p, v in sorted(reach.routed_refs - VERIFIED.routed_refs)),
        *(f"the API's imports reach {m}" for m in sorted(reach.api_reach)),
        *(f"the probes service's imports reach {m}" for m in sorted(reach.probes_reach)),
        *(
            f"service {name!r} runs the api image as {command!r}"
            for name, command in sorted(reach.image_commands.items())
            if VERIFIED.image_commands.get(name) != command
        ),
    ]
    if reach.api_command != VERIFIED.api_command:
        paths.append(f"the api runs {reach.api_command!r}")
    return paths


def outside_parties(allowlist: dict[str, object], reach: Reach) -> list[str]:
    """Why the no-vendor sentences may no longer be true; empty while they are."""
    tiers = allowlist["tiers"]
    assert isinstance(tiers, dict)
    reasons = [
        f"PHI-path egress row {row.get('name')!r} ({row.get('purpose_id')})"
        for row in tiers.get("phi_path") or []
        if row.get("purpose_id") not in PHI_PATH_PURPOSES_OUTSIDE_THE_TEXTS
    ]
    providers = yaml.safe_load(
        (REPO / "infra" / "model-lanes" / "providers.yaml").read_text(encoding="utf-8")
    )
    hosted_rows = {provider["egress_row"] for provider in providers["providers"]}
    hosted = sorted(
        str(row["name"])
        for rows in tiers.values()
        for row in rows or []
        if row.get("name") in hosted_rows or row.get("purpose_id") == "hosted_model_inference"
    )
    if hosted:
        reasons.extend(f"hosted rows {hosted} reachable: {path}" for path in _paths(reach))
    return reasons


def _index() -> SyntheticLegalIndex:
    return SyntheticLegalIndex(REPO / SYNTHETIC_LEGAL_ROOT, data_class=TenantDataClass.SYNTHETIC)


def names_sms_processor(body: str) -> bool:
    """Whether a text names the SMS processor, with its country, where it lists
    who sees the data (before "Nerede:")."""
    if "Kimler görür:" not in body or "Nerede:" not in body:
        return False
    section = body[body.index("Kimler görür:") : body.index("Nerede:")]
    return SMS_PROCESSOR in section and SMS_PROCESSOR_COUNTRY in section


# --- the tripwire ------------------------------------------------------------------------


def test_the_no_vendor_sentences_are_in_the_texts() -> None:
    index = _index()
    for document_id, sentence in NO_VENDOR_SENTENCES.items():
        assert sentence in index.entry(document_id).body, document_id


def test_no_outside_party_can_receive_what_the_texts_say_none_receives() -> None:
    reasons = outside_parties(_allowlist(), _reach())
    assert reasons == [], (
        f"{reasons}: name each recipient (verified legal entity and country) in "
        f"{sorted(NO_VENDOR_SENTENCES)}, re-sign the synthetic index (files/06 §2.1), "
        "and only then move the verified facts"
    )


def test_the_verified_facts_are_exactly_today_s_tree() -> None:
    """Exact, not a superset: a verified set wider than the tree could absorb
    a new path silently."""
    assert _reach() == VERIFIED


def test_hosted_rows_are_listed_today() -> None:
    """The hosted half only matters while hosted rows are listed. If they are
    removed (ADR-035 reverts), this pin goes and the hosted half is dormant."""
    tiers = _allowlist()["tiers"]
    assert isinstance(tiers, dict)
    listed = {
        row["name"] for row in tiers["dev"] if row.get("purpose_id") == "hosted_model_inference"
    }
    assert listed == {"openai-api", "elevenlabs-api"}


# --- the SMS processor: named exactly where its data is spoken of ----------------------


def test_the_sms_row_is_the_netgsm_host_on_its_own_proxy() -> None:
    """The one PHI-path row is Netgsm's, and the api reaches it only through
    the SMS-only proxy on ``sms-out`` (ADR-042): the compose names that proxy
    for the api, and the platform binds the SMS purpose to that one URL."""
    tiers = _allowlist()["tiers"]
    assert isinstance(tiers, dict)
    rows = [row for row in tiers.get("phi_path") or [] if row["purpose_id"] == "sms_otp_delivery"]
    assert [row["host"] for row in rows] == [SMS_HOST]
    compose = yaml.safe_load((REPO / "infra/staging/compose.yaml").read_text(encoding="utf-8"))
    api_env = compose["services"]["api"]["environment"]
    proxy = DEDICATED_PERSONAL_PROXIES[EgressPurpose.SMS_OTP_DELIVERY]
    assert api_env["INTAKE_SMS_EGRESS_PROXY_URL"] == proxy == "http://sms-egress:3128"
    assert VERIFIED.api_peers["sms-out"] == {"sms-egress"}
    assert VERIFIED.external["sms-wan"] == {"sms-egress"}


@pytest.mark.parametrize(("document_id", "named"), sorted(SMS_PROCESSOR_TEXTS.items()))
def test_only_the_text_that_speaks_of_sign_in_names_the_sms_processor(
    document_id: str, named: bool
) -> None:
    """core says what the sign-in number is (held apart from the record) and
    who sends the code; voice, lane:affect and documents carry no sign-in data
    and name no SMS processor (files/06 §2.1 parity, exactly per text)."""
    body = _index().entry(document_id).body
    assert names_sms_processor(body) is named
    assert ("Netgsm" in body) is named


def test_the_core_text_says_exactly_what_reaches_the_sms_processor() -> None:
    body = _index().entry("acik_riza.core").body
    assert "Giriş için kullandığınız telefon numarası bu kayıtlara yazılmaz." in body
    assert "Kaydınız, numaranızdan üretilen bir takma kimlikle tutulur." in body
    assert "Bu gönderim, bu onaydan önce, giriş sırasında yapılır." in body
    assert "Bu şirkete yalnızca numaranız ve kod gider; yanıtlarınız gitmez." in body
    # the us-east-1 leg (INT-528 evidence, ADR-042): the number goes out from this host
    assert "Giriş için yazdığınız numara da bu sunucu üzerinden Netgsm'e gider." in body


def test_the_wire_carries_exactly_the_number_and_the_code() -> None:
    """The core sentence "yalnızca numaranız ve kod gider" rests on the adapter:
    the body is exactly the sender name, the message and the number, and the
    message template has one field, the code (``otp_netgsm.py`` l.131, l.277)."""
    request = NetgsmOtpRequest(msgheader="SENDER", msg="m", no="5550000000")
    assert set(request.as_wire()) == {"msgheader", "msg", "no"}
    fields = {name for _, name, _, _ in string.Formatter().parse(SMS_TEMPLATE) if name}
    assert fields == {"code"}


@pytest.mark.parametrize(
    "body",
    [
        "Kimler görür:\nSiz görürsünüz.\n\nNerede:\nABD.",
        f"Kimler görür:\n{SMS_PROCESSOR} gönderir.\n\nNerede:\nABD.",
        "Kimler görür:\nSiz.\n\nNerede:\n"
        f"{SMS_PROCESSOR} gönderir. Bu şirket {SMS_PROCESSOR_COUNTRY}.",
    ],
    ids=["unnamed", "no-country", "named-in-the-wrong-section"],
)
def test_a_text_that_does_not_name_the_processor_where_recipients_are_listed_fails(
    body: str,
) -> None:
    assert not names_sms_processor(body)


def _calls_to(source: str, name: str) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Attribute) and node.func.attr == name)
            or (isinstance(node.func, ast.Name) and node.func.id == name)
        )
    ]


def test_the_clip_lane_carries_only_the_scripted_catalogue() -> None:
    """ElevenLabs is reached from one place, and that place hands it the
    scripted-catalogue predicate. The predicate's caller builds it from the
    compiled catalogue (``dev_voice_guard.ScriptedCatalogue.admits``)."""
    sources = python_sources()
    vendor_calls = {
        path: calls
        for path, source in sources.items()
        if not path.startswith("packages/hosted-lanes/")
        and (calls := _calls_to(source, "hosted_clip_tts_from_env"))
    }
    assert set(vendor_calls) == {_CLIP_LANE}
    ((call,),) = vendor_calls.values()
    admits = {kw.arg: kw.value for kw in call.keywords}["admits"]
    assert isinstance(admits, ast.Name) and admits.id == "admits"

    lane_calls = {
        path: calls
        for path, source in sources.items()
        if path != _CLIP_LANE and (calls := _calls_to(source, "hosted_clip_lane"))
    }
    assert set(lane_calls) == {"services/api/src/intake_api/dev_voice.py"}
    ((lane_call,),) = lane_calls.values()
    predicate = {kw.arg: kw.value for kw in lane_call.keywords}["admits"]
    assert ast.unparse(predicate) == "catalogue.admits"
    dev_voice = sources["services/api/src/intake_api/dev_voice.py"]
    assert "catalogue = scripted_catalogue_from_env()" in dev_voice


# --- near misses -----------------------------------------------------------------------


def _with_row(tier: str, row: dict[str, str]) -> dict[str, object]:
    allowlist = _allowlist()
    tiers = allowlist["tiers"]
    assert isinstance(tiers, dict)
    tiers[tier] = [*(tiers.get(tier) or []), row]
    return allowlist


@pytest.mark.parametrize(
    ("tier", "row", "trips"),
    [
        ("phi_path", {"name": "sms-otp-2", "purpose_id": "sms_otp_delivery"}, False),
        ("phi_path", {"name": "asr-vendor", "purpose_id": "clinical_transcription"}, True),
        ("dev", {"name": "another-llm", "purpose_id": "hosted_model_inference"}, False),
    ],
)
def test_a_new_row_trips_only_when_it_can_carry_patient_data(
    tier: str, row: dict[str, str], trips: bool
) -> None:
    """Row side. A second sign-in SMS row passes this half (the host pin above
    holds it to Netgsm), any other PHI-path row trips, and one more hosted row
    on today's tree passes: nothing hands it patient data."""
    assert bool(outside_parties(_with_row(tier, row), VERIFIED)) is trips


def _console_with(extra: str) -> Reach:
    """Today's tree with one line appended to the model-lanes console."""
    sources = dict(python_sources())
    sources[_CONSOLE] = sources[_CONSOLE] + "\n" + extra + "\n"
    return _reach(sources)


@pytest.mark.parametrize(
    "line",
    [
        "router.hosted.backends[provider].chat_json(data_block=answers)",
        "router.hosted.backends[provider].transcribe(audio)",
        "speak = getattr(backend, 'speech')",
    ],
)
def test_an_api_call_into_a_hosted_backend_trips(line: str) -> None:
    assert outside_parties(_allowlist(), _console_with(line))


def test_the_console_s_probe_only_call_is_quiet() -> None:
    """Near miss: another identity probe through the same backends map adds no
    path, because a probe sends only the model id."""
    reach = _console_with("healthy = router.hosted.backends.get(provider).probe(model.wire)")
    assert outside_parties(_allowlist(), reach) == []


def test_an_importlib_literal_naming_a_gateway_trips() -> None:
    sources = dict(python_sources())
    sources["services/api/src/intake_api/hosted_extract.py"] = (
        'import importlib\nlane = importlib.import_module("intake_hosted_lanes.openai_compat")\n'
    )
    assert outside_parties(_allowlist(), _reach(sources))
    sources["services/api/src/intake_api/hosted_extract.py"] = (
        'runner = __import__("intake_voice_runtime.extraction.lanes")\n'
    )
    assert outside_parties(_allowlist(), _reach(sources))


def test_a_gateway_reached_transitively_trips() -> None:
    """The API imports a first-party module that imports a dispatcher."""
    sources = dict(python_sources())
    sources["packages/intake_platform/src/intake_platform/answers_out.py"] = (
        "from voice_clips.lanes import LaneRoutedTtsGateway\n"
    )
    sources["services/api/src/intake_api/answers_route.py"] = (
        "from intake_platform.answers_out import LaneRoutedTtsGateway\n"
    )
    reach = _reach(sources)
    assert reach.api_reach == {"voice_clips.lanes"}
    assert outside_parties(_allowlist(), reach)


def test_a_gateway_reached_by_the_probes_service_trips() -> None:
    """The probes service runs the api's image. If its code ever imports a
    gateway, transitively, it is a path like the API's own."""
    sources = dict(python_sources())
    sources["packages/intake_platform/src/intake_platform/answers_out.py"] = (
        "from voice_clips.lanes import LaneRoutedTtsGateway\n"
    )
    sources["services/probes/src/intake_probes/answers_probe.py"] = (
        "from intake_platform.answers_out import LaneRoutedTtsGateway\n"
    )
    reach = _reach(sources)
    assert reach.probes_reach == {"voice_clips.lanes"}
    assert reach.api_reach == frozenset()
    assert outside_parties(_allowlist(), reach)


def test_the_probes_service_as_deployed_is_quiet() -> None:
    """Near miss: probes on backend and edge, running intake_probes.app, with no
    gateway in reach, adds no path."""
    reach = _reach()
    assert reach.api_peers["backend"] >= {"probes"} and reach.api_peers["edge"] >= {"probes"}
    assert all("probes" not in members for members in reach.external.values())
    assert outside_parties(_allowlist(), reach) == []


def _with_peer(network: str, member: str) -> Reach:
    peers = {**VERIFIED.api_peers, network: VERIFIED.api_peers.get(network, frozenset()) | {member}}
    return replace(VERIFIED, api_peers=peers)


def _with_external(network: str, member: str) -> Reach:
    external = {
        **VERIFIED.external,
        network: VERIFIED.external.get(network, frozenset()) | {member},
    }
    return replace(VERIFIED, external=external)


@pytest.mark.parametrize(
    "moved",
    [
        replace(VERIFIED, services=VERIFIED.services | {"voice-runtime", "livekit"}),  # INT-515
        _with_external("sms-wan", "api"),  # the api gets its own way off the host
        _with_external("vendor", "api"),
        _with_peer("outbound", "sms-egress"),  # the two proxies' networks bridged
        _with_peer("sms-out", "egress-proxy"),
        _with_peer("backend", "voice-runtime"),
        # the probes service re-pointed at the voice runtime, a second service on
        # the api image, probes gaining a way out, or probes reaching a gateway
        replace(
            VERIFIED,
            image_commands={"probes": (("python", "-m", "intake_voice_runtime"), None)},
        ),
        replace(
            VERIFIED, image_commands={**VERIFIED.image_commands, "worker": (("celery",), None)}
        ),
        _with_external("vendor", "probes"),
        _with_peer("outbound", "probes"),
        replace(VERIFIED, probes_reach=frozenset({"voice_clips.lanes"})),
        replace(VERIFIED, api_command=(["python", "-m", "intake_voice_runtime"], None, None)),
        replace(
            VERIFIED,
            dispatchers=VERIFIED.dispatchers
            | {"packages/intake_platform/src/intake_platform/documents_llm.py"},
        ),
    ],
)
def test_a_deploy_side_path_trips_while_hosted_rows_are_listed(moved: Reach) -> None:
    reasons = outside_parties(_allowlist(), moved)
    assert reasons
    assert all("openai-api" in reason and "elevenlabs-api" in reason for reason in reasons)


def test_the_same_path_is_quiet_when_no_hosted_row_is_listed() -> None:
    """Path side: voice-runtime on a host with no hosted row sends nothing to
    a vendor, so the sentences stay true."""
    allowlist = _allowlist()
    tiers = allowlist["tiers"]
    assert isinstance(tiers, dict)
    tiers["dev"] = [
        row for row in tiers["dev"] if row.get("purpose_id") != "hosted_model_inference"
    ]
    moved = replace(VERIFIED, services=VERIFIED.services | {"voice-runtime"})
    assert outside_parties(allowlist, moved) == []
