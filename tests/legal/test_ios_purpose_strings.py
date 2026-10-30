"""INT-592 — the iOS purpose strings App Review reads (GitHub #1000).

App Store processing rejected TestFlight build 6 with ITMS-90683: the bundle's
Info.plist had no NSHealthUpdateUsageDescription. The HealthKit library links
the write APIs, so Apple requires the key even though this app requests no
write type. INT-420 had set the plugin option to ``false``, which writes no key.

The key now carries a string, and three things must hold for it:

* it is in the base Info.plist (the plugin option) and localised through
  ``expo.locales`` like the microphone and camera strings, with tr as the source;
* it is patient-facing copy, so it passes PolicyGuard (invariant 2) and the B1
  bound the rest of the copy is measured against;
* the store-label inventory accounts for it: a declared capability with no row
  fails ``facts.unclassified_permissions``, and this one carries no personal
  data because the app writes nothing.

Whether the string is *true* (it must deny writing, near misses included) is
asserted in apps/mobile/e2e/brand.spec.ts, beside the code it describes.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Final

import pytest
from intake_platform.store import facts as facts_mod
from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.talker.guard_lexicons.tr import B1_MAX_WORDS_PER_SENTENCE
from intake_voice_runtime.talker.policy_guard import (
    FormOfAddress,
    PolicyGuard,
    policy_guard_for,
)

REPO = Path(__file__).resolve().parents[2]
MOBILE = REPO / "apps" / "mobile"
APP_JSON = MOBILE / "app.json"
LOCALE_DIR = MOBILE / "src" / "locales"
LOCALES = (LOCALE_DIR / "app-tr.json", LOCALE_DIR / "app-en.json")
LOCALE_TS = MOBILE / "src" / "lib" / "i18n" / "locale.ts"
HEALTHKIT_PLUGIN = "@kingstinct/react-native-healthkit"
HEALTH_KEYS: Final[tuple[str, ...]] = (
    "NSHealthShareUsageDescription",
    "NSHealthUpdateUsageDescription",
)

#: Purpose strings over the B1 bound, recorded rather than rewritten (the
#: i18n gate's rule). This set may only shrink. It is empty: the INT-208
#: share string was one 19-word sentence, and the legal review of INT-592
#: replaced it with three short ones.
B1_LENGTH_FINDINGS: Final[frozenset[str]] = frozenset()

#: PolicyGuard's findings, read as (violation class, key). This set may only
#: shrink. ``jargon`` is also the guard's length arm (tests/release/
#: test_i18n_complete.py records welcome.body that way); the share string's
#: entry went with its length.
POLICYGUARD_FINDINGS: Final[frozenset[tuple[str, str]]] = frozenset()


def _plist(locale: str) -> dict[str, str]:
    data: dict[str, str] = json.loads((LOCALE_DIR / f"app-{locale}.json").read_text("utf-8"))
    return data


def _purpose_strings(strings: dict[str, str]) -> dict[str, str]:
    return {
        key: value
        for key, value in strings.items()
        if key.startswith("NS") and key.endswith("UsageDescription")
    }


def _healthkit_options() -> dict[str, object]:
    plugins = json.loads(APP_JSON.read_text("utf-8"))["expo"]["plugins"]
    for plugin in plugins:
        if isinstance(plugin, list) and plugin[0] == HEALTHKIT_PLUGIN:
            options: dict[str, object] = plugin[1]
            return options
    raise AssertionError("the HealthKit config plugin is not registered")


@pytest.fixture(scope="module")
def guard() -> PolicyGuard:
    return policy_guard_for(
        locale="tr", profile=VoiceProfile.RESIDENCY_TR, form_of_address=FormOfAddress.SIZ
    )


def test_the_base_info_plist_carries_both_health_strings() -> None:
    """ITMS-90683 reads the base Info.plist, which the plugin option writes.
    ``false`` (INT-420) and an empty string both leave the key out."""
    options = _healthkit_options()
    for key in HEALTH_KEYS:
        value = options.get(key)
        assert isinstance(value, str) and value.strip(), f"{key} is {value!r}"


def test_the_base_strings_are_the_turkish_catalogues() -> None:
    """tr is the source of truth (invariant 5): the base Info.plist and the tr
    localisation cannot say two different things."""
    options = _healthkit_options()
    tr = _plist("tr")
    for key in HEALTH_KEYS:
        assert options[key] == tr.get(key), key


def test_every_purpose_string_is_localised_in_both_catalogues() -> None:
    tr = _purpose_strings(_plist("tr"))
    en = _purpose_strings(_plist("en"))
    assert set(tr) == set(en)
    assert set(HEALTH_KEYS) <= set(tr)
    for key in tr:
        assert en[key].strip(), key
        assert en[key] != tr[key], f"{key} is not translated"


def test_the_purpose_strings_pass_policyguard(guard: PolicyGuard) -> None:
    found = {
        (violation.violation_class.value, key)
        for key, value in _purpose_strings(_plist("tr")).items()
        for sentence in guard.sentences(value)
        for violation in guard.inspect_sentence(sentence)
    }
    assert found == set(POLICYGUARD_FINDINGS), (
        f"PolicyGuard findings in the iOS purpose strings: new "
        f"{sorted(found - POLICYGUARD_FINDINGS)}, resolved {sorted(POLICYGUARD_FINDINGS - found)}"
    )
    # The write string is new copy, so it carries no finding of any class.
    assert not {key for _, key in found} & {"NSHealthUpdateUsageDescription"}


def test_the_b1_length_findings_are_exactly_the_recorded_ones(guard: PolicyGuard) -> None:
    over = {
        key
        for key, value in _purpose_strings(_plist("tr")).items()
        for sentence in guard.sentences(value)
        if len(sentence.split()) > B1_MAX_WORDS_PER_SENTENCE
    }
    assert over == set(B1_LENGTH_FINDINGS), (
        f"above the B1 bound of {B1_MAX_WORDS_PER_SENTENCE} words: "
        f"new {sorted(over - B1_LENGTH_FINDINGS)}, resolved {sorted(B1_LENGTH_FINDINGS - over)}"
    )


def test_the_write_string_is_declared_and_classified_as_carrying_no_data() -> None:
    declared = facts_mod.declared_app_permissions(APP_JSON, LOCALES)
    assert "NSHealthUpdateUsageDescription" in declared
    entry = facts_mod.PERMISSION_CLASSIFICATION["NSHealthUpdateUsageDescription"]
    assert entry.flow_id is None, "the app writes nothing, so no flow moves data"
    assert "writes nothing" in entry.reason


def test_near_miss_a_false_option_declares_no_key(tmp_path: Path) -> None:
    """The shape INT-420 shipped. The inventory reads ``false`` as undeclared,
    which is exactly what Apple saw: no key at all."""
    config = json.loads(APP_JSON.read_text("utf-8"))
    for plugin in config["expo"]["plugins"]:
        if isinstance(plugin, list) and plugin[0] == HEALTHKIT_PLUGIN:
            plugin[1]["NSHealthUpdateUsageDescription"] = False
    app_json = tmp_path / "app.json"
    app_json.write_text(json.dumps(config), "utf-8")
    empty = tmp_path / "empty.json"
    empty.write_text("{}", "utf-8")
    declared = facts_mod.declared_app_permissions(app_json, (empty,))
    assert "NSHealthUpdateUsageDescription" not in declared
    assert "NSHealthShareUsageDescription" in declared


# --- INT-595: the binary declares only the languages the app offers ----------------------


def _offered_locales(source: str) -> set[str]:
    """The locales LOCALE_REGISTRY registers, read from locale.ts."""
    block = source.split("export const LOCALE_REGISTRY", 1)[1].split("});", 1)[0]
    return set(re.findall(r"^  ([A-Za-z-]+): \{", block, flags=re.MULTILINE))


def _declares_only_offered(expo: dict[str, object], offered: set[str]) -> bool:
    locales = expo.get("locales")
    ios = expo.get("ios")
    plist = ios.get("infoPlist", {}) if isinstance(ios, dict) else {}
    return (
        isinstance(locales, dict)
        and set(locales) == offered
        and isinstance(plist, dict)
        and plist.get("CFBundleDevelopmentRegion") in offered
    )


def test_the_binary_declares_only_the_languages_the_app_offers() -> None:
    """INT-595 (GitHub #1008). The App Store's Languages row is read from the binary's
    .lproj folders (Apple Technical Q&A QA1828, updated 2016-03-23), and expo.locales
    writes one folder per key, so expo.locales equals LOCALE_REGISTRY. The development
    region is one of those languages too: iOS falls back to it when none of a reader's
    languages is offered, so the purpose strings stay Turkish for every reader.

    Near miss: build 7's app.json (tr and en, no development region) is refused."""
    expo = json.loads(APP_JSON.read_text(encoding="utf-8"))["expo"]
    offered = _offered_locales(LOCALE_TS.read_text(encoding="utf-8"))
    assert offered == {"tr"}
    assert _declares_only_offered(expo, offered)
    assert expo["ios"]["infoPlist"]["CFBundleDevelopmentRegion"] == "tr"
    build_7 = {
        "locales": {"tr": "./src/locales/app-tr.json", "en": "./src/locales/app-en.json"},
        "ios": {"infoPlist": {"ITSAppUsesNonExemptEncryption": False}},
    }
    assert not _declares_only_offered(build_7, offered)
    english_region = {
        "locales": {"tr": "./src/locales/app-tr.json"},
        "ios": {"infoPlist": {"CFBundleDevelopmentRegion": "en"}},
    }
    assert not _declares_only_offered(english_region, offered)
