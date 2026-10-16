"""INT-529 — the tripwire on the synthetic texts' "no outside party" sentences.

Three synthetic texts say that the patient's audio, answers and documents reach
no outside company. Each sentence is true only while nothing on the synthetic
host can send that data to a vendor. Two routes could make them false:

- **A PHI-path egress row.** The one admitted purpose is ``sms_otp_delivery``
  (INT-528's Netgsm row). It carries the sign-in number and code, never audio,
  answers or documents, so none of these sentences speaks about it.
- **A hosted model lane that a deployed process routes patient data through.**
  ADR-035 lists the hosted vendors' rows (``openai-api``, ``elevenlabs-api``;
  INT-442), and the console can switch a lane to a hosted provider. A row alone
  moves no patient data, though. On the synthetic host today, the API reaches
  a hosted vendor only through the clip lane (server-verified scripted catalogue
  text, ``NON_PERSONAL``; ``intake_api.dev_voice_guard``) and the console's
  identity probes. The gateways that would carry a patient's audio or answers
  (``model_lanes.dispatch`` and its three importers) run in ``voice-runtime``,
  which ``infra/staging/compose.yaml`` does not deploy.

So the hosted half of the tripwire fires when a hosted row is listed **and**
any one of these holds:
1. the synthetic host gains a service the texts were not verified against;
2. a new module routes calls through ``dispatch``;
3. the API imports a routed gateway.

When it fires, the fix is not to widen these sets. The texts must name each
recipient by its verified legal entity and country (files/06 §2.1's
consent/vendor parity), the synthetic index must be re-signed, and every grant
is re-prompted. Only then may the set move. INT-515 (voice-runtime and an SFU
on this host, GitHub #877) is the planned change that fires it.

Narrowed from "any listed hosted row" on the INT-529 refresh (16 Oct 2026),
when INT-442 listed the rows without moving any patient data. The
legal-reviewer verifies the narrowing (docs/evidence/INT-529.md §12).
"""

from __future__ import annotations

import ast
from collections.abc import Iterable
from pathlib import Path

import pytest
import yaml
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

#: The synthetic host's services, as the sentences were verified against them on
#: 16 Oct 2026. None hosts a routed lane gateway.
VERIFIED_SYNTHETIC_SERVICES = frozenset(
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
        "caddy",
    }
)

#: The modules that route a call through ``intake_platform.model_lanes.dispatch``,
#: so a hosted lane can carry what they are given. The API imports none of them.
VERIFIED_DISPATCHERS = frozenset(
    {
        "packages/voice-clips/src/voice_clips/lanes.py",
        "services/voice-runtime/src/intake_voice_runtime/adapters/lanes.py",
        "services/voice-runtime/src/intake_voice_runtime/extraction/lanes.py",
    }
)
_DISPATCH_MODULE = "intake_platform.model_lanes.dispatch"
_LANES_PACKAGE = "intake_platform.model_lanes"


def _allowlist() -> dict[str, object]:
    loaded: dict[str, object] = yaml.safe_load(
        (REPO / "infra" / "security" / "egress-allowlist.yaml").read_text(encoding="utf-8")
    )
    return loaded


def _staging_services() -> frozenset[str]:
    compose = yaml.safe_load((REPO / "infra" / "staging" / "compose.yaml").read_text("utf-8"))
    return frozenset(compose["services"])


def _imports(path: Path) -> list[tuple[str, tuple[str, ...]]]:
    """``(module, names)`` for every import statement in one file."""
    found: list[tuple[str, tuple[str, ...]]] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module:
            found.append((node.module, tuple(alias.name for alias in node.names)))
        elif isinstance(node, ast.Import):
            found.extend((alias.name, ()) for alias in node.names)
    return found


def _source_trees() -> list[Path]:
    return sorted([*REPO.glob("packages/*/src"), *REPO.glob("services/*/src")])


def _routes_through_dispatch(imports: Iterable[tuple[str, tuple[str, ...]]]) -> bool:
    return any(
        module == _DISPATCH_MODULE or (module == _LANES_PACKAGE and "dispatch" in names)
        for module, names in imports
    )


def _dispatchers() -> frozenset[str]:
    out: set[str] = set()
    for tree in _source_trees():
        for path in tree.rglob("*.py"):
            relative = path.relative_to(REPO).as_posix()
            if "/intake_platform/model_lanes/" in relative:
                continue
            if _routes_through_dispatch(_imports(path)):
                out.add(relative)
    return frozenset(out)


def _module_name(relative: str) -> str:
    """``packages/x/src/a/b.py`` → ``a.b``."""
    inside = relative.split("/src/", 1)[1]
    return inside.removesuffix(".py").replace("/", ".")


def _api_routed_imports(dispatchers: frozenset[str]) -> list[str]:
    """Every import in ``services/api/src`` of a routed gateway or of dispatch."""
    gateways = {_module_name(path) for path in dispatchers}
    hits: list[str] = []
    for path in sorted((REPO / "services" / "api" / "src").rglob("*.py")):
        for module, names in _imports(path):
            routed = (
                module in gateways
                or module.startswith("intake_voice_runtime")
                or _routes_through_dispatch([(module, names)])
            )
            if routed:
                hits.append(f"{path.relative_to(REPO).as_posix()} imports {module}")
    return hits


def outside_parties(
    allowlist: dict[str, object],
    *,
    services: frozenset[str],
    dispatchers: frozenset[str],
    api_routed_imports: list[str],
) -> list[str]:
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
    if not hosted:
        return reasons
    paths = [
        *(
            f"service {name!r} on the synthetic host"
            for name in sorted(services - VERIFIED_SYNTHETIC_SERVICES)
        ),
        *(f"{path} routes through dispatch" for path in sorted(dispatchers - VERIFIED_DISPATCHERS)),
        *api_routed_imports,
    ]
    reasons.extend(f"hosted rows {hosted} reachable through {path}" for path in paths)
    return reasons


def _current() -> list[str]:
    dispatchers = _dispatchers()
    return outside_parties(
        _allowlist(),
        services=_staging_services(),
        dispatchers=dispatchers,
        api_routed_imports=_api_routed_imports(dispatchers),
    )


def test_the_no_vendor_sentences_are_in_the_texts() -> None:
    index = SyntheticLegalIndex(REPO / SYNTHETIC_LEGAL_ROOT, data_class=TenantDataClass.SYNTHETIC)
    for document_id, sentence in NO_VENDOR_SENTENCES.items():
        assert sentence in index.entry(document_id).body, document_id


def test_no_outside_party_can_receive_what_the_texts_say_none_receives() -> None:
    reasons = _current()
    assert reasons == [], (
        f"{reasons}: name each recipient (verified legal entity and country) in "
        f"{sorted(NO_VENDOR_SENTENCES)}, re-sign the synthetic index (files/06 §2.1), "
        "and only then move the verified sets"
    )


def test_the_verified_sets_are_exactly_today_s_tree() -> None:
    """Both sets must be exact. A set that is wider than the tree could absorb
    a new path silently."""
    dispatchers = _dispatchers()
    assert _staging_services() == VERIFIED_SYNTHETIC_SERVICES
    assert dispatchers == VERIFIED_DISPATCHERS
    assert _api_routed_imports(dispatchers) == []


def test_hosted_rows_are_listed_today() -> None:
    """The narrowed half only matters while hosted rows are listed. If they are
    removed (ADR-035 reverts), this pin goes and the hosted half is dormant."""
    tiers = _allowlist()["tiers"]
    assert isinstance(tiers, dict)
    assert {
        row["name"] for row in tiers["dev"] if row.get("purpose_id") == "hosted_model_inference"
    } == {
        "openai-api",
        "elevenlabs-api",
    }


def _with_row(tier: str, row: dict[str, str]) -> dict[str, object]:
    allowlist = _allowlist()
    tiers = allowlist["tiers"]
    assert isinstance(tiers, dict)
    tiers[tier] = [*(tiers.get(tier) or []), row]
    return allowlist


@pytest.mark.parametrize(
    ("tier", "row", "trips"),
    [
        ("phi_path", {"name": "sms-otp", "purpose_id": "sms_otp_delivery"}, False),
        ("phi_path", {"name": "asr-vendor", "purpose_id": "clinical_transcription"}, True),
        ("dev", {"name": "another-llm", "purpose_id": "hosted_model_inference"}, False),
    ],
)
def test_a_new_row_trips_only_when_it_can_carry_patient_data(
    tier: str, row: dict[str, str], trips: bool
) -> None:
    """Near misses on the row side. The sign-in SMS row passes, and any other
    PHI-path row trips. A further hosted row on today's tree passes too, because
    no deployed process routes patient data to a hosted lane."""
    dispatchers = _dispatchers()
    reasons = outside_parties(
        _with_row(tier, row),
        services=_staging_services(),
        dispatchers=dispatchers,
        api_routed_imports=_api_routed_imports(dispatchers),
    )
    assert bool(reasons) is trips


@pytest.mark.parametrize(
    ("services", "dispatchers", "api_imports"),
    [
        # INT-515: voice-runtime and an SFU on the synthetic host
        (VERIFIED_SYNTHETIC_SERVICES | {"voice-runtime", "livekit"}, VERIFIED_DISPATCHERS, []),
        # a new module routes calls through dispatch (documents, say)
        (
            VERIFIED_SYNTHETIC_SERVICES,
            VERIFIED_DISPATCHERS
            | {"packages/intake_platform/src/intake_platform/documents_llm.py"},
            [],
        ),
        # the API imports a routed gateway
        (
            VERIFIED_SYNTHETIC_SERVICES,
            VERIFIED_DISPATCHERS,
            ["services/api/src/intake_api/x.py imports voice_clips.lanes"],
        ),
    ],
)
def test_a_path_for_patient_data_trips_while_hosted_rows_are_listed(
    services: frozenset[str], dispatchers: frozenset[str], api_imports: list[str]
) -> None:
    reasons = outside_parties(
        _allowlist(), services=services, dispatchers=dispatchers, api_routed_imports=api_imports
    )
    assert reasons
    assert all("openai-api" in reason and "elevenlabs-api" in reason for reason in reasons)


def test_the_same_path_is_quiet_when_no_hosted_row_is_listed() -> None:
    """Near miss on the path side: voice-runtime on a host with no hosted row
    sends nothing to a vendor, so the sentences stay true."""
    allowlist = _allowlist()
    tiers = allowlist["tiers"]
    assert isinstance(tiers, dict)
    tiers["dev"] = [
        row for row in tiers["dev"] if row.get("purpose_id") != "hosted_model_inference"
    ]
    reasons = outside_parties(
        allowlist,
        services=VERIFIED_SYNTHETIC_SERVICES | {"voice-runtime"},
        dispatchers=VERIFIED_DISPATCHERS,
        api_routed_imports=[],
    )
    assert reasons == []


def test_the_api_import_scan_sees_a_routed_gateway(tmp_path: Path) -> None:
    """The scanner itself, on a file that imports dispatch by name."""
    path = tmp_path / "probe.py"
    path.write_text("from intake_platform.model_lanes import LaneRouter, dispatch\n", "utf-8")
    assert _routes_through_dispatch(_imports(path))
    path.write_text("from intake_platform.model_lanes import LaneRouter\n", "utf-8")
    assert not _routes_through_dispatch(_imports(path))
