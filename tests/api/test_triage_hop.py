"""INT-446 — the rules-engine hop the app's dialogue and typed lanes call.

What this file pins:
- every bound answer set is evaluated by ``protocols.triage.evaluate_triage``
  over the served set (invariant 1), and a RED comes back as the data-channel
  packet shape, identifiers and axes only (invariant 21);
- a near miss — the same slot, one differing value — does not fire, and
  neither does the right value with its tense anchor undated;
- the winning rule's id is the one whose register AND script the engine
  returned, not ``result.rules[0]`` (a severity tie is broken on register);
- the RED-script catalog is verbatim ``tr`` text, and the ON_SITE script never
  carries the 112 affordance, whatever the pack says;
- fail closed: no set, ``served: false``, missing sign-off or a draft rule is
  a 503 on both routes — never a GREEN, never an empty catalog;
- authentication and the core consent scope apply; input is bounded;
- the recorded packets under tests/fixtures/triage_hop/ ARE the route's output
  — the mobile end-to-end test replays those bytes, so the two halves cannot
  drift;
- the answer-to-trigger time is inside the 300 ms RED budget (files/02 §8.2).
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml
from api_harness import ADMIN_TOKEN, PATIENT_TOKEN, ApiHarness, build_harness
from intake_api.consent_guard import unguarded_data_routes

REPO_ROOT = Path(__file__).resolve().parents[2]
SIGNED = REPO_ROOT / "tests" / "fixtures" / "protocols" / "compile" / "life_threat_signed.yaml"
GOLDEN = REPO_ROOT / "tests" / "fixtures" / "triage_hop"
# INT-465: the committed generic RED is active (CD-24), so every test serves it.
GENERIC = REPO_ROOT / "packages" / "protocols" / "generic" / "generic_red.yaml"

REFERENCE_TIME = "2026-08-29T10:00:00+03:00"
FIRING = {"ziyaret.basvuru_nedeni": "sentetik_yasamsal", "sure_dakika": "2026-08-29"}
RED_BUDGET_MS = 300.0


def _set(tmp_path: Path, edit: Any = None, name: str = "set.yaml") -> Path:
    doc = yaml.safe_load(SIGNED.read_text(encoding="utf-8"))
    if edit is not None:
        edit(doc)
    path = tmp_path / name
    path.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


@pytest.fixture()
def harness(tmp_path: Path) -> Iterator[ApiHarness]:
    yield from build_harness(
        tmp_path,
        token_patient=PATIENT_TOKEN,
        token_admin=ADMIN_TOKEN,
        triage_generic_red_path=GENERIC,
        triage_rules_path=SIGNED,
    )


def _evaluate(harness: ApiHarness, answers: dict[str, Any], location: str = "REMOTE") -> Any:
    response = harness.client.post(
        "/v1/triage/evaluate",
        headers=harness.patient(),
        json={"location": location, "reference_time": REFERENCE_TIME, "answers": answers},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_red_answer_returns_the_data_channel_packet(harness: ApiHarness) -> None:
    body = _evaluate(harness, FIRING)
    assert body == {
        "kind": "red_trigger",
        "ruleId": "rf.sentetik_yasamsal",
        "register": "ALERT",
        "location": "REMOTE",
        "scriptId": "rf.sentetik_yasamsal.remote",
    }


def test_near_miss_value_does_not_fire(harness: ApiHarness) -> None:
    near = {**FIRING, "ziyaret.basvuru_nedeni": "sentetik_yasamsal_degil"}
    assert _evaluate(harness, near) == {"kind": "triage_level", "level": "GREEN"}


def test_undated_anchor_does_not_fire(harness: ApiHarness) -> None:
    undated = {"ziyaret.basvuru_nedeni": "sentetik_yasamsal"}
    assert _evaluate(harness, undated) == {"kind": "triage_level", "level": "GREEN"}


@pytest.mark.parametrize("location", ["REMOTE", "ON_SITE", "UNKNOWN"])
def test_every_location_names_a_pre_positioned_entry(harness: ApiHarness, location: str) -> None:
    body = _evaluate(harness, FIRING, location)
    assert body["location"] == location
    catalog = harness.client.get("/v1/triage/red-scripts", headers=harness.patient()).json()
    table = catalog["questions"] if location == "UNKNOWN" else catalog["scripts"]
    assert body["scriptId"] in table


def test_catalog_is_verbatim_and_on_site_has_no_112(harness: ApiHarness) -> None:
    response = harness.client.get("/v1/triage/red-scripts", headers=harness.patient())
    assert response.status_code == 200, response.text
    catalog = response.json()
    remote = catalog["scripts"]["rf.sentetik_yasamsal.remote"]
    on_site = catalog["scripts"]["rf.sentetik_yasamsal.on_site"]
    unknown = catalog["questions"]["rf.sentetik_yasamsal.unknown"]
    assert remote == {
        "primary": "CALL_112",
        "show112": True,
        "actionTr": "Hemen yardım isteyin.",
        "doNotsTr": ["Yalnız kalmayın."],
        "whyTr": "Bu bir sentetik test metnidir.",
    }
    assert on_site["show112"] is False
    assert on_site["actionTr"] == "Görevlilere haber verin."
    assert unknown == {
        "askTr": "Şu anda hastanede misiniz?",
        "onYes": "ON_SITE",
        "onNo": "REMOTE",
        "onNoAnswer": "REMOTE",
    }


def test_a_set_authorising_112_on_site_is_refused(tmp_path: Path) -> None:
    """Under ON_SITE the 112 affordance is absent (invariant 21): a set that
    authorises it is not served at all, so no catalog can carry it."""

    def authorise(doc: dict[str, Any]) -> None:
        doc["rules"][0]["action"]["ON_SITE"]["show_112"] = True

    path = _set(tmp_path, authorise)
    for harness in build_harness(
        tmp_path,
        token_patient=PATIENT_TOKEN,
        token_admin=ADMIN_TOKEN,
        triage_generic_red_path=GENERIC,
        triage_rules_path=path,
    ):
        _assert_closed(harness)


def test_winner_is_the_rule_whose_register_and_script_the_engine_chose(tmp_path: Path) -> None:
    """Two RED rules of equal acuity fire. ``result.rules`` lists them by id,
    so its head is the ALERT rule; the engine's winner is the SILENT one
    (the more restrictive register wins, files/02 §5.3)."""

    def twin(doc: dict[str, Any]) -> None:
        alert = doc["rules"][0]
        silent = json.loads(json.dumps(alert, default=str))
        alert["id"] = "rf.a_sentetik_alert"
        silent["id"] = "rf.b_sentetik_silent"
        silent["register"] = "SILENT"
        silent["action"]["REMOTE"]["action_tr"] = {"tr": "Sentetik sessiz yönerge."}
        doc["rules"] = [alert, silent]

    path = _set(tmp_path, twin)
    for harness in build_harness(
        tmp_path,
        token_patient=PATIENT_TOKEN,
        token_admin=ADMIN_TOKEN,
        triage_generic_red_path=GENERIC,
        triage_rules_path=path,
    ):
        body = _evaluate(harness, FIRING)
        assert body["ruleId"] == "rf.b_sentetik_silent"
        assert body["register"] == "SILENT"
        assert body["scriptId"] == "rf.b_sentetik_silent.remote"


def _unserved(doc: dict[str, Any]) -> None:
    doc["served"] = False
    doc["serve_blocked_reason"] = "sentetik"


def _unsigned(doc: dict[str, Any]) -> None:
    doc["clinical_signoff"]["reviewer_name"] = None


def _draft(doc: dict[str, Any]) -> None:
    doc["rules"][0]["status"] = "draft_needs_source"


@pytest.mark.parametrize("edit", [_unserved, _unsigned, _draft])
def test_an_unservable_set_fails_closed(tmp_path: Path, edit: Any) -> None:
    path = _set(tmp_path, edit)
    for harness in build_harness(
        tmp_path,
        token_patient=PATIENT_TOKEN,
        token_admin=ADMIN_TOKEN,
        triage_generic_red_path=GENERIC,
        triage_rules_path=path,
    ):
        _assert_closed(harness)


def test_no_set_and_an_unreadable_set_fail_closed(tmp_path: Path) -> None:
    for path in (None, tmp_path / "absent.yaml"):
        for harness in build_harness(
            tmp_path,
            token_patient=PATIENT_TOKEN,
            token_admin=ADMIN_TOKEN,
            triage_generic_red_path=GENERIC,
            triage_rules_path=path,
        ):
            _assert_closed(harness)


def _assert_closed(harness: ApiHarness) -> None:
    catalog = harness.client.get("/v1/triage/red-scripts", headers=harness.patient())
    evaluated = harness.client.post(
        "/v1/triage/evaluate",
        headers=harness.patient(),
        json={"location": "REMOTE", "reference_time": REFERENCE_TIME, "answers": FIRING},
    )
    for response in (catalog, evaluated):
        assert response.status_code == 503
        assert response.json() == {"error": "triage_unconfigured"}


def test_authentication_and_consent_apply(harness: ApiHarness) -> None:
    bare = harness.client.post(
        "/v1/triage/evaluate",
        json={"location": "REMOTE", "reference_time": REFERENCE_TIME, "answers": FIRING},
    )
    assert bare.status_code == 401
    assert harness.client.get("/v1/triage/red-scripts").status_code == 401
    assert unguarded_data_routes(harness.client.app) == []  # type: ignore[arg-type]
    harness.revoke_consent("core")
    revoked = harness.client.post(
        "/v1/triage/evaluate",
        headers=harness.patient(),
        json={"location": "REMOTE", "reference_time": REFERENCE_TIME, "answers": FIRING},
    )
    assert revoked.status_code == 403


@pytest.mark.parametrize(
    "body",
    [
        {"reference_time": REFERENCE_TIME, "answers": FIRING},
        {"location": "SOMEWHERE", "reference_time": REFERENCE_TIME, "answers": FIRING},
        {"location": "REMOTE", "reference_time": "2026-08-29T10:00:00", "answers": FIRING},
        {"location": "REMOTE", "reference_time": REFERENCE_TIME, "answers": {"Bad Ref": "x"}},
        {
            "location": "REMOTE",
            "reference_time": REFERENCE_TIME,
            "answers": {f"s{i}": "x" for i in range(513)},
        },
        {"location": "REMOTE", "reference_time": REFERENCE_TIME, "answers": {"s": "x" * 2001}},
        {"location": "REMOTE", "reference_time": REFERENCE_TIME, "answers": FIRING, "extra": 1},
    ],
)
def test_input_is_validated_at_the_boundary(harness: ApiHarness, body: dict[str, Any]) -> None:
    response = harness.client.post("/v1/triage/evaluate", headers=harness.patient(), json=body)
    assert response.status_code == 422


def test_recorded_packets_are_the_routes_own_output(harness: ApiHarness) -> None:
    """The mobile end-to-end test replays these files; this pins them to the
    route, so the device is tested against what the engine really says."""
    catalog = harness.client.get("/v1/triage/red-scripts", headers=harness.patient()).json()
    recorded_catalog = json.loads((GOLDEN / "red_catalog.json").read_text(encoding="utf-8"))
    assert {k: v for k, v in catalog.items() if k != "version"} == recorded_catalog
    recorded = json.loads((GOLDEN / "exchanges.json").read_text(encoding="utf-8"))
    names = []
    for exchange in recorded["exchanges"]:
        response = harness.client.post(
            "/v1/triage/evaluate", headers=harness.patient(), json=exchange["request"]
        )
        assert response.status_code == 200, exchange["name"]
        assert response.json() == exchange["response"], exchange["name"]
        names.append(exchange["name"])
    # Both halves of the e2e need a RED per location and two near misses.
    assert names == [
        "red_remote",
        "red_on_site",
        "red_unknown",
        "near_miss_value",
        "near_miss_undated",
    ]


def test_answer_to_trigger_is_inside_the_red_budget(harness: ApiHarness) -> None:
    _evaluate(harness, FIRING)  # warm the lazy set load, as the device's catalog fetch does
    samples: list[float] = []
    for _ in range(50):
        started = time.perf_counter()
        _evaluate(harness, FIRING)
        samples.append((time.perf_counter() - started) * 1000.0)
    samples.sort()
    p95 = samples[int(len(samples) * 0.95) - 1]
    assert p95 < RED_BUDGET_MS


SIM = GOLDEN / "life_threat_sim.yaml"


@pytest.mark.parametrize(
    ("answer", "fires"),
    [("2026-01-01", True), ("2026-01-02", False), ("sentetik", False)],
)
def test_the_simulator_set_fires_on_the_typed_free_note_only(
    tmp_path: Path, answer: str, fires: bool
) -> None:
    """The set the INT-446 simulator run serves: a typed answer to the app's
    free-note question `extra` fires it; a near miss (one differing digit, or
    an undated word) does not."""
    for harness in build_harness(
        tmp_path,
        token_patient=PATIENT_TOKEN,
        token_admin=ADMIN_TOKEN,
        triage_generic_red_path=GENERIC,
        triage_rules_path=SIM,
    ):
        body = _evaluate(harness, {"extra": answer}, "UNKNOWN")
        if fires:
            assert body["ruleId"] == "rf.sentetik_sim"
            assert body["scriptId"] == "rf.sentetik_sim.unknown"
        else:
            assert body == {"kind": "triage_level", "level": "GREEN"}


def _draft_generic(tmp_path: Path) -> Path:
    doc = yaml.safe_load(GENERIC.read_text(encoding="utf-8"))
    doc["status"] = "draft_needs_source"
    doc["source_gap"] = "sentetik: the register row is withdrawn"
    path = tmp_path / "generic_draft.yaml"
    path.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


@pytest.mark.parametrize("generic", ["draft", "absent"])
def test_nothing_is_served_while_the_generic_red_is_draft_or_absent(
    tmp_path: Path, generic: str
) -> None:
    """INT-453 serve precondition: a blank generic RED never reaches a live
    tenant. A draft generic, or none, serves nothing. The near miss is every
    other test here: with the active CD-24 generic, the very same set serves."""
    path = _draft_generic(tmp_path) if generic == "draft" else tmp_path / "absent.yaml"
    for harness in build_harness(
        tmp_path,
        token_patient=PATIENT_TOKEN,
        token_admin=ADMIN_TOKEN,
        triage_generic_red_path=path,
        triage_rules_path=SIGNED,
    ):
        _assert_closed(harness)


def test_the_catalog_pre_positions_the_generic_red(harness: ApiHarness) -> None:
    catalog = harness.client.get("/v1/triage/red-scripts", headers=harness.patient()).json()
    assert catalog["scripts"]["base.generic_red.remote"]["show112"] is True
    assert catalog["scripts"]["base.generic_red.on_site"]["show112"] is False
    unknown = catalog["questions"]["base.generic_red.unknown"]
    assert unknown["askTr"] == "Şu anda hastanede misiniz?"
    # INT-465: the generic is CD-24's copy, rendered (no markup reaches the screen).
    assert catalog["scripts"]["base.generic_red.remote"]["actionTr"] == (
        "Hemen 112 Acil Çağrı Merkezi'ni arayın."
    )
    assert catalog["scripts"]["base.generic_red.on_site"]["actionTr"] == (
        "Acil Servis'e gidin. Randevuyu beklemeyin. Görevlilere haber verildi."
    )


# --- INT-465: the synthetic host's rule set, signed with the synthetic-only test key ---------

LIFE_THREAT = REPO_ROOT / "files" / "protocols" / "base.life_threat.yaml"
SIGNATURE = REPO_ROOT / "packages" / "protocols" / "signing" / "red_rule_set.synthetic.json"
CARDIAC = "rf.chest_pain_cardiac_features"
HOST = "i-0e489e48739f5de98"


def _synthetic(
    tmp_path: Path,
    *,
    kind: str = "synthetic",
    rules: Path = LIFE_THREAT,
    signature: Path | None = SIGNATURE,
    deployment: str | None = HOST,
) -> Iterator[ApiHarness]:
    return build_harness(
        tmp_path,
        token_patient=PATIENT_TOKEN,
        token_admin=ADMIN_TOKEN,
        triage_rules_path=rules,
        triage_signature_path=signature,
        triage_tenant_kind=kind,
        triage_deployment=deployment,
    )


def test_a_synthetic_tenant_serves_the_test_key_signed_life_threat_set(tmp_path: Path) -> None:
    """The owner's 3 Oct 2026 decision with D18: on the synthetic host the test-key
    signature stands in for the physician's sign-off (HB-C1), for simulated patients
    only. Drafts are never served and every script is rendered."""
    for harness in _synthetic(tmp_path):
        response = harness.client.get("/v1/triage/red-scripts", headers=harness.patient())
        assert response.status_code == 200, response.text
        catalog = response.json()
        assert catalog["scripts"][f"{CARDIAC}.remote"]["actionTr"] == "Hemen 112'yi arayın."
        assert catalog["scripts"][f"{CARDIAC}.on_site"]["show112"] is False
        assert "base.generic_red.on_site" in catalog["scripts"]
        assert not any(key.startswith("rf.crisis_disclosure") for key in catalog["scripts"])
        assert not any(key.startswith("rf.paediatric_airway") for key in catalog["scripts"])
        # Near miss: an answer set with no chest pain stays GREEN.
        near = _evaluate(harness, {"chest_pain.character": "baskı"})
        assert near == {"kind": "triage_level", "level": "GREEN"}


@pytest.mark.parametrize("kind", ["real", "", "production", "Synthetic"])
def test_any_non_synthetic_tenant_rejects_the_test_key_signed_set(
    tmp_path: Path, kind: str
) -> None:
    """The same files and the same signature: anything but the exact synthetic
    kind is a real tenant, and a real tenant refuses the test key."""
    for harness in _synthetic(tmp_path, kind=kind):
        _assert_closed(harness)


def test_a_real_tenant_refuses_a_test_signature_even_beside_a_clinically_signed_set(
    tmp_path: Path,
) -> None:
    """A test-key signature never helps on a real tenant. Configured beside a set that
    carries a complete sign-off, it makes the set unservable rather than trusted. Near
    miss: the same set with no signature configured serves (the ``harness`` fixture)."""
    for harness in _synthetic(tmp_path, kind="real", rules=SIGNED):
        _assert_closed(harness)


def test_a_synthetic_tenant_on_another_host_fails_closed(tmp_path: Path) -> None:
    """The committed signature names i-0e489e48739f5de98. The same files on another
    host do not serve. Near miss: the first synthetic test above serves on the bound host."""
    for harness in _synthetic(tmp_path, deployment="i-0123456789abcdef0"):
        _assert_closed(harness)


def test_a_synthetic_tenant_without_a_signature_fails_closed(tmp_path: Path) -> None:
    for harness in _synthetic(tmp_path, signature=None):
        _assert_closed(harness)


def test_a_synthetic_tenant_with_a_malformed_signature_fails_closed(tmp_path: Path) -> None:
    broken = tmp_path / "envelope.json"
    broken.write_bytes(b"\xff not an envelope")
    for harness in _synthetic(tmp_path, signature=broken):
        _assert_closed(harness)


def test_a_synthetic_tenant_refuses_a_changed_byte(tmp_path: Path) -> None:
    tampered = tmp_path / "base.life_threat.yaml"
    tampered.write_bytes(LIFE_THREAT.read_bytes() + b"\n")
    for harness in _synthetic(tmp_path, rules=tampered):
        _assert_closed(harness)
