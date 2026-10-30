"""INT-536 F1 — the "who sees what" lines above the consent texts are true.

The consent detail screen shows ``consent.who.<purpose>`` directly above the
bound legal text (``apps/mobile/src/app/(tabs)/me/consents/[purpose].tsx``).
The consent list shows ``consent.who.core`` under the core row
(``components/ConsentList.tsx``). Four of these lines said things the code
does not do:
- **voice** said "Veriler Türkiye'deki sunucularda kalır". That is false on the
  synthetic us-east-1 host, and nothing in the production deployment
  guarantees it.
- **lane:affect** and **lane:linguistic** said "yalnızca hekiminiz görür". No
  lane output reaches a clinician (invariant 11).
- **core** said only the patient and the approved doctor see the answers. A
  RED, though, raises an alert in the clinic Safety inbox without a share
  (INT-537 G1).

The lines now state only what holds on every host. Where the data is processed
and who receives it is host-dependent, so the line defers to the bound text,
which says it. This suite pins each line and the code fact it rests on, so a
change on either side fails here instead of drifting apart. The sentence-by-
sentence citations are in ``docs/evidence/INT-536.md`` §2.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
from clinical_schemas.observers import InteractionState, Lane, ObserverState
from intake_platform.safety_inbox.model import InboxEntry
from intake_platform.store.facts import OFF_SCHEMA_FLOWS
from intake_voice_runtime.observers.contract import LANE_SPECS, ObserverField

REPO = Path(__file__).resolve().parents[2]
CATALOGUES = {
    "tr": REPO / "apps/mobile/src/lib/i18n/tr.ts",
    "en": REPO / "apps/mobile/src/lib/i18n/en.ts",
}
_ENTRY = re.compile(r'^\s*"(consent\.who\.[A-Za-z]+)":\s*\n?\s*"((?:[^"\\]|\\.)*)",?\s*$', re.M)

#: Words that would claim a place. Where data is processed depends on the host,
#: so a who-line never names one. The bound text does.
_PLACE_CLAIMS = re.compile(
    r"Türkiye|Turkey|\bABD\b|\bUSA?\b|United States|\bAWS\b|Amazon|[Yy]urt ?(?:içi|dışı)"
)

EXPECTED = {
    "tr": {
        "consent.who.core": (
            "Yanıtlarınızı siz görürsünüz. Hekiminiz notunuzu yalnızca siz paylaşırsanız "
            "görür. Acil bir durum işaretinde klinik personeli, "
            "sağlık yanıtlarınızı içermeyen bir uyarı görür. Bilgilerinizin nerede işlendiği "
            "izin metninde yazar."
        ),
        "consent.who.voice": (
            "Sesiniz görüşme sırasında yazıya dökülür; ses kaydı saklanmaz. Sesinizin "
            "nerede işlendiği ve kimlere gittiği izin metninde yazar."
        ),
        "consent.who.laneAffect": (
            "Ses tonunuzdan çıkan ipuçları yalnızca görüşmenin hızını ve akışını ayarlar. "
            "Hekiminize gitmez, notunuza yazılmaz ve size gösterilmez."
        ),
        "consent.who.laneLinguistic": (
            "Yazıya dökülen metinden çıkan ipuçları hekiminize gitmez ve notunuza yazılmaz."
        ),
    },
    "en": {
        "consent.who.core": (
            "You see your answers. Your doctor sees your note only if you share it. On "
            "an emergency flag, clinic staff see an alert that does not "
            "contain your health answers. Where your data is processed is stated in the consent "
            "text."
        ),
        "consent.who.voice": (
            "Your voice is turned into text during the session; no audio recording is "
            "kept. Where your voice is processed and who receives it is stated in the "
            "consent text."
        ),
        "consent.who.laneAffect": (
            "Cues drawn from your tone of voice only adjust the pace and flow of the "
            "session. They do not go to your doctor, are not written into your note and "
            "are not shown to you."
        ),
        "consent.who.laneLinguistic": (
            "Cues drawn from the transcribed text do not go to your doctor and are not "
            "written into your note."
        ),
    },
}


def _who_lines(locale: str) -> dict[str, str]:
    text = CATALOGUES[locale].read_text(encoding="utf-8")
    return {key: value for key, value in _ENTRY.findall(text)}


def place_claims(line: str) -> list[str]:
    return _PLACE_CLAIMS.findall(line)


@pytest.mark.parametrize("locale", sorted(EXPECTED))
def test_the_rewritten_lines_are_the_ones_shipped(locale: str) -> None:
    lines = _who_lines(locale)
    for key, value in EXPECTED[locale].items():
        assert lines[key] == value, key


@pytest.mark.parametrize("locale", sorted(EXPECTED))
def test_no_who_line_names_a_place(locale: str) -> None:
    lines = _who_lines(locale)
    assert len(lines) == 10, sorted(lines)
    assert {key: place_claims(value) for key, value in lines.items() if place_claims(value)} == {}


@pytest.mark.parametrize(
    ("line", "claims"),
    [
        (
            "Sesiniz yalnızca görüşme sırasında işlenir; kayıt saklanmaz. "
            "Veriler Türkiye'deki sunucularda kalır.",
            True,
        ),
        ("Data stays on servers in Türkiye.", True),
        ("Bu test ortamı ABD'deki bir AWS sunucusunda çalışır.", True),
        ("Sesinizin nerede işlendiği ve kimlere gittiği izin metninde yazar.", False),
        ("Your answers are used to evaluate the service.", False),
    ],
)
def test_the_place_check_catches_the_old_voice_line(line: str, claims: bool) -> None:
    """Near miss for the check above: the shipped voice line before INT-536 is
    caught, and the deferral to the text is not."""
    assert bool(place_claims(line)) is claims


@pytest.mark.parametrize("key", ["consent.who.laneAffect", "consent.who.laneLinguistic"])
def test_no_lane_line_says_the_doctor_sees_it(key: str) -> None:
    tr = _who_lines("tr")[key]
    assert "hekiminiz görür" not in tr
    assert "hekiminize gitmez" in tr.lower()
    assert "do not go to your doctor" in _who_lines("en")[key]


# --- the code facts the lines rest on ----------------------------------------------------


def test_affect_cues_die_inside_m1() -> None:
    """laneAffect: the cues only adjust pace and flow, reach no doctor and no
    note, and are never shown. Only the closed six-field InteractionState
    leaves M1, and ObserverState has no affect field at all."""
    assert LANE_SPECS[Lane.AFFECT].field is ObserverField.M1_INTERNAL
    assert set(InteractionState.model_fields) == {
        "pace",
        "modality",
        "break_offer",
        "confirm_by_card",
        "repeat_request",
        "third_party_present",
    }
    assert set(ObserverState.model_fields) == {
        "session_id",
        "interaction",
        "linguistic_markers",
        "asr_quality",
        "engagement",
    }


def _src_files() -> list[Path]:
    trees = [*REPO.glob("packages/*/src"), *REPO.glob("services/*/src")]
    return sorted(path for tree in trees for path in tree.rglob("*.py"))


def _readers_of(name: str) -> set[str]:
    """Files that read ``name`` as an attribute or pass it as a keyword."""
    found: set[str] = set()
    for path in _src_files():
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            hit = (isinstance(node, ast.Attribute) and node.attr == name) or (
                isinstance(node, ast.keyword) and node.arg == name
            )
            if hit:
                found.add(path.relative_to(REPO).as_posix())
    return found


def test_linguistic_markers_never_leave_the_observers() -> None:
    """laneLinguistic: the markers are written to ObserverState by the
    observer store, and nothing outside the observers package reads them. No
    note, no clinician surface."""
    observers = "services/voice-runtime/src/intake_voice_runtime/observers/"
    assert {
        path for path in _readers_of("linguistic_markers") if not path.startswith(observers)
    } == set()


def test_nothing_builds_the_speech_measures_block_into_a_note() -> None:
    """The one note block that could carry lane-derived speech measures
    (``konusma_ozellikleri``, files/04 §5) has no producer: no call passes it."""
    callers = {
        path
        for path in _readers_of("konusma_ozellikleri")
        if not path.endswith(
            (
                "clinical_schemas/note.py",
                "clinical_schemas/mappers/document.py",
                "note/composer.py",
                "note/render.py",
                "summary/cards.py",
            )
        )
    }
    assert callers == set()


def test_the_red_alert_carries_ids_not_answers() -> None:
    """core: the clinic Safety inbox entry holds ids, the rule codes, the time
    and the register. It has no field an answer could sit in, and it forbids
    extra fields."""
    assert set(InboxEntry.model_fields) == {
        "schema_version",
        "entry_id",
        "tenant_id",
        "session_id",
        "visit_id",
        "kind",
        "rule_ids",
        "source_ref",
        "created_at",
        "acknowledged_at",
        "acknowledged_by",
        "register",
    }
    assert InboxEntry.model_config.get("extra") == "forbid"


def test_no_audio_recording_is_kept() -> None:
    """voice: the inventory's off-schema voice flow is never persisted
    (invariant 3, proved by tests/voice/test_audio_retention_guard.py)."""
    flow = OFF_SCHEMA_FLOWS["voice_audio"]
    assert flow.persisted is False
    assert "never written" in flow.annotation["retention"]
