"""INT-494: CD-111 applied to the served cardiac RED rule, checked on the served artefact.

CD-111 (INT-468, #813) decides the do-not lines of ``rf.chest_pain_cardiac_features``:
REMOTE line 1 changes to the sourced driving line, line 3 changes to a conditional
prohibition, and the nil-by-mouth line goes in both locations, with no medicine line in
its place. INT-494 applies both locations together, in record order. CD-111 is D18 scope:
simulated patients only, and a licensed physician's review is required before any real
patient.

These goldens read what the synthetic AWS host would serve, not a hand-built fixture:
``files/protocols/base.life_threat.yaml``, the CD-24 generic RED and the committed
test-key signature, through ``intake_api.triage_rules.load_served_red_rules`` under a
synthetic tenant. Every golden carries a near-miss negative control. The engine half (the
axis goldens pin each location's do-not list, and three mutations prove it) lives in
tests/safety/triage_goldens_structure.py and tests/safety/triage_mutations.py.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
from clinical_schemas.triage import RedRegister
from intake_api.triage_rules import CatalogOut, ServedRedRules, load_served_red_rules
from intake_platform.red_signature import (
    COMMITTED_SIGNATURE,
    COMMITTED_TRUST_REGISTRY,
    RedSignatureRefused,
    load_signature,
    load_trust_registry,
    verify_red_rule_set,
)
from intake_platform.red_tenant import TenantKind, TenantRedConfig
from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.talker.policy_guard import PolicyGuard, policy_guard_for
from protocols.clinical_decisions import load_register
from protocols.compile.tr_orthography import TrExpansionError
from protocols.red_render import RedRenderError, assert_speakable_red, spoken_red_text
from protocols.types import EK4Level, RedFlagRoute

REPO = Path(__file__).resolve().parents[2]
LIFE_THREAT = REPO / "files" / "protocols" / "base.life_threat.yaml"
GENERIC = REPO / "packages" / "protocols" / "generic" / "generic_red.yaml"
PRODUCT_SPEC = REPO / "files" / "02_PRODUCT_SPEC.md"
SYNTHETIC = TenantRedConfig(kind=TenantKind.SYNTHETIC, deployment="i-0e489e48739f5de98")
CARDIAC = "rf.chest_pain_cardiac_features"
REMOTE = f"{CARDIAC}.remote"
ON_SITE = f"{CARDIAC}.on_site"
UNKNOWN = f"{CARDIAC}.unknown"
SERVED_IDS = ("rf.chest_pain_cardiac_features", "rf.chest_pain_no_cardiac_history")
TWELVE = re.compile(r"112|yüz on iki", re.IGNORECASE)
MARKUP = re.compile(r"[*{}\[\]]")
#: A do-not line is a prohibition: the bare negative imperative plural (-mAyIn).
PROHIBITION = re.compile(r"m[ae]y[ıi]n\b")
#: Food, drink or medicine by mouth. "için", "içinde" and "içeri" are not drinking.
BY_MOUTH = re.compile(
    r"\b(?:yiy|yeme|yemey|yiyecek|içme|içmey|içecek|ağ[ıi]?z|yut|çiğne|aspirin|ilaç|hap"
    r"|tablet|sıvı|tüket)|\baç\s+kal|\bsu\s+(?:al|iç|ver)",
    re.IGNORECASE,
)
REMOVED = "Bir şey yiyip içmeyin."


@pytest.fixture(scope="module")
def served() -> ServedRedRules:
    loaded = load_served_red_rules(
        LIFE_THREAT, GENERIC, signature_path=COMMITTED_SIGNATURE, tenant=SYNTHETIC
    )
    assert loaded is not None, "the synthetic host's signed rule set must serve"
    return loaded


@pytest.fixture(scope="module")
def catalog(served: ServedRedRules) -> CatalogOut:
    return served.catalog


@pytest.fixture(scope="module")
def guard() -> PolicyGuard:
    return policy_guard_for(locale="tr", profile=VoiceProfile.RESIDENCY_TR)


def _cd111() -> Mapping[str, Any]:
    return load_register()["CD-111"].value


def _decided(location: str) -> tuple[str, ...]:
    return tuple(_cd111()["decided_lists"][location])


def _original(location: str) -> tuple[str, ...]:
    return tuple(line["from"] for line in _cd111()["do_nots"] if line["location"] == location)


def _cardiac_texts(catalog: CatalogOut) -> list[str]:
    texts: list[str] = []
    for script_id in (REMOTE, ON_SITE):
        script = catalog.scripts[script_id]
        texts.extend([script.actionTr, *script.doNotsTr, *([script.whyTr] if script.whyTr else [])])
    return texts


def test_c01_remote_serves_the_decided_list_in_record_order(catalog: CatalogOut) -> None:
    assert catalog.scripts[REMOTE].doNotsTr == _decided("REMOTE")
    assert catalog.scripts[REMOTE].doNotsTr == (
        "Hastaneye kendiniz araba kullanarak gitmeyin.",
        "Yanınızda biri varsa sizi yalnız bırakmasına izin vermeyin.",
    )
    # Near miss: the pre-CD-111 list carried the nil-by-mouth line; it is not served,
    # and neither is the decided list in another order.
    assert REMOVED in _original("REMOTE")
    assert catalog.scripts[REMOTE].doNotsTr != _original("REMOTE")
    assert catalog.scripts[REMOTE].doNotsTr != tuple(reversed(_decided("REMOTE")))


def test_c02_on_site_serves_the_decided_list_and_no_112(catalog: CatalogOut) -> None:
    on_site = catalog.scripts[ON_SITE]
    assert on_site.doNotsTr == _decided("ON_SITE")
    assert REMOVED not in on_site.doNotsTr
    assert on_site.show112 is False and on_site.primary == "GO_TO_IN_HOUSE_ACIL"
    assert not any(
        TWELVE.search(text) for text in (on_site.actionTr, *on_site.doNotsTr, on_site.whyTr or "")
    )
    # Near miss: the REMOTE branch of the same rule carries 112, as a control and a number.
    assert catalog.scripts[REMOTE].show112 is True
    assert TWELVE.search(catalog.scripts[REMOTE].actionTr)
    assert _original("ON_SITE") != on_site.doNotsTr and len(_original("ON_SITE")) == 3


def test_c03_no_served_cardiac_line_speaks_of_food_drink_or_medicine(
    catalog: CatalogOut,
) -> None:
    assert [text for text in _cardiac_texts(catalog) if BY_MOUTH.search(text)] == []
    assert _cd111()["medication_line"]["added"] is False
    # Near miss: the removed line and a medicine line both trip the same check, and the
    # served "için" and "içeri" do not.
    assert BY_MOUTH.search(REMOVED)
    assert BY_MOUTH.search("Ambulansı beklerken bir aspirin çiğneyin.")
    assert not BY_MOUTH.search("öncelik sırası için bekletilmez; içeri alınır")


def do_not_problems(text: str, guard: PolicyGuard) -> list[str]:
    """Every way one served do-not line can break the RED copy rules."""
    problems: list[str] = []
    if not PROHIBITION.search(text):
        problems.append("not a prohibition (no -mAyIn verb)")
    if MARKUP.search(text):
        problems.append("authoring markup")
    try:
        if spoken_red_text(text, acil_location_tr=None) != text:
            problems.append("expanded for speech, so it carried a numeral (invariant 22)")
    except (RedRenderError, TrExpansionError):
        problems.append("no speakable form (invariant 22)")
    violations = guard.filter(text, scripted=True).violations
    if violations:
        problems.append(f"PolicyGuard: {sorted(v.violation_class for v in violations)}")
    return problems


def test_c04_every_served_cardiac_do_not_is_a_clean_spoken_prohibition(
    catalog: CatalogOut, guard: PolicyGuard
) -> None:
    for script_id in (REMOTE, ON_SITE):
        for text in catalog.scripts[script_id].doNotsTr:
            assert do_not_problems(text, guard) == [], (script_id, text)
            assert_speakable_red(text)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Yanınızdaki kişiden yardım isteyin.", "not a prohibition"),
        ("Hastaneye 1 saat içinde gitmeyin.", "invariant 22"),
        ("**Hastaneye** kendiniz araba kullanarak gitmeyin.", "markup"),
        ("Kalp krizi geçiriyorsunuz, araba kullanmayın.", "PolicyGuard"),
    ],
)
def test_c04_near_misses_each_fail(text: str, expected: str, guard: PolicyGuard) -> None:
    problems = do_not_problems(text, guard)
    assert any(expected in problem for problem in problems), problems


def test_c05_level_route_register_and_locations_are_unchanged(
    served: ServedRedRules, catalog: CatalogOut
) -> None:
    rule = next(r for r in served.rules if r.id == CARDIAC)
    assert rule.level is EK4Level.KIRMIZI_K2
    assert rule.route is RedFlagRoute.EMERGENCY_NOW
    assert rule.register is RedRegister.ALERT
    remote = catalog.scripts[REMOTE]
    assert (remote.primary, remote.show112) == ("CALL_112", True)
    assert remote.actionTr == "Hemen 112'yi arayın."
    question = catalog.questions[UNKNOWN]
    assert question.askTr == "Şu anda hastanede misiniz?"
    assert (question.onYes, question.onNo, question.onNoAnswer) == ("ON_SITE", "REMOTE", "REMOTE")
    assert tuple(sorted(r.id for r in served.rules)) == SERVED_IDS
    # Near miss: the two locations differ on exactly the 112 axis.
    assert catalog.scripts[ON_SITE].show112 is not remote.show112


def _signed_problem(life_threat_bytes: bytes) -> str | None:
    try:
        verify_red_rule_set(
            load_signature(COMMITTED_SIGNATURE),
            registry=load_trust_registry(COMMITTED_TRUST_REGISTRY),
            tenant=SYNTHETIC,
            life_threat_bytes=life_threat_bytes,
            generic_red_bytes=GENERIC.read_bytes(),
            served_rule_ids=SERVED_IDS,
        )
    except RedSignatureRefused as refused:
        return refused.code
    return None


def _restore_original(raw: str, location: str) -> str:
    decided, original = _decided(location), _original(location)
    block = "".join(f'            - "{line}"\n' for line in decided)
    assert raw.count(block) == 1, location
    return raw.replace(block, "".join(f'            - "{line}"\n' for line in original))


def test_c06_the_signature_binds_the_applied_bytes() -> None:
    raw = LIFE_THREAT.read_bytes()
    envelope = json.loads(COMMITTED_SIGNATURE.read_text(encoding="utf-8"))
    assert envelope["payload"]["life_threat"]["sha256"] == hashlib.sha256(raw).hexdigest()
    assert _signed_problem(raw) is None
    # Near miss: the same file with the pre-CD-111 lines restored, in either location,
    # is no longer signed; the old text was never re-signed.
    text = raw.decode("utf-8")
    for location in ("REMOTE", "ON_SITE"):
        restored = _restore_original(text, location).encode("utf-8")
        assert _signed_problem(restored) == "life_threat_digest_mismatch", location


def test_c06_a_real_tenant_still_refuses_the_applied_set() -> None:
    for kind in (kind for kind in TenantKind if kind is not TenantKind.SYNTHETIC):
        assert (
            load_served_red_rules(
                LIFE_THREAT,
                GENERIC,
                signature_path=COMMITTED_SIGNATURE,
                tenant=TenantRedConfig(kind=kind),
            )
            is None
        )


def worked_bullets(spec: str, heading: str) -> list[str]:
    """The "Lütfen yapmayın" bullets of one worked example in files/02 §5.3."""
    block = spec.split(heading, 1)[1].split("**Neden**", 1)[0]
    listed = block.split("**Lütfen yapmayın**", 1)[1]
    return re.findall(r"^> • (.+)$", listed, re.M)


def _served_lines(lines: Sequence[str]) -> list[str]:
    return [line.rstrip(".") for line in lines]


def test_c07_the_files_02_worked_on_site_example_shows_the_served_list(
    catalog: CatalogOut,
) -> None:
    spec = PRODUCT_SPEC.read_text(encoding="utf-8")
    on_site = worked_bullets(spec, "**Worked `ALERT` text — adult chest pain")
    assert _served_lines(on_site) == _served_lines(catalog.scripts[ON_SITE].doNotsTr)
    assert REMOVED not in on_site
    # Near miss: the same parser reads the paediatric CALM example's four lines, so an
    # empty match cannot pass the check above.
    assert len(worked_bullets(spec, "**Worked `CALM` text — paediatric airway")) == 4
