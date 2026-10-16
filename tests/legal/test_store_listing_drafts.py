"""INT-482 — the Önvizit store listing copy: drafts, gates, sources, register.

GitHub #825, acceptance in short: an EAS Metadata ``store.config.json`` for the
App Store in Turkish and English under the name Önvizit, generated from repo
sources with no invented claim and with legal links only to hash-bound
docs/legal texts; the Play listing text in the same source; App Review notes
for a health app; the age-rating answers recorded; the release checklist
linking all of it. Pending legal-lane review. This suite holds the copy; the
render, the links and the submission answers are in
``test_store_submission_drafts.py``, the privacy answers in
``test_store_privacy_answers.py``.

Why the tests are shaped this way:

- **The copy is a draft for the legal lane** (``docs/legal/drafts/store/``).
  HUMAN_BLOCKERS HB-L21 says nothing is *published* until the seller identity
  and the audio determination are answered, and docs/legal/drafts/README.md is
  the repo's one pattern for agent-prepared legal text: a banner, no loader,
  promotion by the owner in a separate PR. So the tests run the **promotion
  dry-run**: each draft is copied to its served name in a temporary tree and
  pushed through the loader, both listing gates, the strict claims scan,
  PolicyGuard and the register rules exactly as it would be after promotion.
- **Every sentence cites a repo file**, so "generated from repo sources, no
  invented claims" is a checked property, not a promise.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType

import pytest
import yaml
from intake_platform.legal import claims
from intake_platform.store import eas_metadata as eas
from intake_platform.store import listing as listing_mod
from intake_voice_runtime.profiles import VoiceProfile
from intake_voice_runtime.talker.policy_guard import FormOfAddress, PolicyGuard, policy_guard_for
from store_drafts_harness import (
    APP_NAME,
    BANNER,
    DRAFTS,
    LOCALES,
    REPO,
    STORES,
    STRICT,
    body,
    cited_path,
    lines,
    listing_source,
    promote,
    store_texts,
)

#: files/06 §7, the static safety line, verbatim. The one sentence in the
#: Turkish copy allowed a bare imperative: CLAUDE.md's register rule inverts
#: inside RED, "where the bare imperative plural (… Arayın …) is correct
#: because ambiguity is the harm".
SAFETY_LINE_TR = "Acil bir durum yaşıyorsanız 112'yi arayın veya en yakın acil servise başvurun."


def _load_i18n_gate() -> ModuleType:
    """The register lexicon has one home (INT-253); read it, never copy it."""
    path = REPO / "tests" / "release" / "test_i18n_complete.py"
    spec = importlib.util.spec_from_file_location("i18n_gate_for_int482", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def guard() -> PolicyGuard:
    return policy_guard_for(
        locale="tr", profile=VoiceProfile.RESIDENCY_TR, form_of_address=FormOfAddress.SIZ
    )


@pytest.fixture(scope="module")
def listings(tmp_path_factory: pytest.TempPathFactory) -> tuple[listing_mod.StoreListing, ...]:
    root = promote(tmp_path_factory.mktemp("promoted"))
    return listing_mod.load_all_listings(listing_mod.listing_dir(root))


# --- 1. the drafts are drafts --------------------------------------------------------------


def test_every_store_draft_starts_with_the_counsel_banner() -> None:
    files = sorted(p for p in DRAFTS.iterdir() if p.is_file())
    assert files
    for path in files:
        assert path.read_text(encoding="utf-8").splitlines()[0].lstrip("#> ").strip() == BANNER


def test_no_served_store_file_carries_the_draft_banner_or_status() -> None:
    """INT-495 promoted the App Store artefacts; a served file that still read as a
    draft, or a draft still sitting beside its served copy, would be two answers."""
    for path in store_texts():
        if DRAFTS in path.parents:
            continue
        text = path.read_text(encoding="utf-8")
        assert BANNER not in text, path.name
        assert body(path)["provenance"]["status"].startswith("served"), path.name
        assert not (DRAFTS / path.name.replace(".yaml", ".draft.yaml")).exists()


def test_the_drafts_readme_indexes_every_store_draft() -> None:
    readme = (REPO / "docs" / "legal" / "drafts" / "README.md").read_text(encoding="utf-8")
    missing = [p.name for p in sorted(DRAFTS.iterdir()) if p.name not in readme]
    assert missing == []


def test_every_draft_says_it_is_pending_legal_lane_review() -> None:
    for path in sorted(DRAFTS.glob("*.yaml")):
        assert body(path)["provenance"]["status"] == "pending legal-lane review", path.name


# --- 2. the promotion dry-run: loader, both listing gates, the strict claims scan ---------


def test_every_listing_draft_promotes_through_the_served_loader(
    listings: tuple[listing_mod.StoreListing, ...],
) -> None:
    assert sorted((x.store, x.locale) for x in listings) == sorted(
        (store, locale) for store in STORES for locale in LOCALES
    )
    for listing in listings:
        assert len(listing.text_hash) == 64
        assert listing_mod.gate_listing(listing) == (), listing.path.name


def test_the_listing_copy_passes_the_strict_claims_scan(
    listings: tuple[listing_mod.StoreListing, ...],
) -> None:
    hits = [
        (listing.path.name, hit.pattern)
        for listing in listings
        for name, value in listing.fields.items()
        for hit in claims.scan_text(value, groups=STRICT, path=name)
    ]
    assert hits == []


def test_the_store_name_is_onvizit_on_every_listing(
    listings: tuple[listing_mod.StoreListing, ...],
) -> None:
    assert {listing.fields["title"] for listing in listings} == {APP_NAME}


def test_the_play_listing_is_the_app_store_listing_from_the_same_source() -> None:
    for locale in LOCALES:
        apple = body(listing_source("app-store", locale))["fields"]
        play = body(listing_source("google-play", locale))["fields"]
        assert play["title"] == apple["title"]
        assert play["full_description"] == apple["description"]


# --- 3. no invented claim: every line cites a file in this repository --------------------


def test_every_line_of_copy_cites_an_existing_repo_file() -> None:
    for store in STORES:
        for locale in LOCALES:
            loaded = body(listing_source(store, locale))
            sources = loaded["sources"]
            for name, value in loaded["fields"].items():
                if isinstance(sources[name], str):
                    assert cited_path(sources[name]).exists(), (store, locale, name)
                    continue
                cited = {row["text"]: row["source"] for row in sources[name]}
                assert set(lines(value)) == set(cited), (store, locale, name)
                for source in cited.values():
                    assert cited_path(source).exists(), (store, locale, name, source)


# --- 4. Turkish copy: PolicyGuard and the siz register ----------------------------------------


def _turkish_fields() -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for store in STORES:
        for name, value in body(listing_source(store, "tr"))["fields"].items():
            if name != "keywords":
                out.append((f"{store}.{name}", value))
    return out


def test_every_turkish_sentence_passes_policyguard(guard: PolicyGuard) -> None:
    found = [
        (where, violation.violation_class.value, sentence)
        for where, value in _turkish_fields()
        for line in lines(value)
        for sentence in guard.sentences(line)
        for violation in guard.inspect_sentence(sentence)
    ]
    assert found == []


def test_the_turkish_copy_never_addresses_the_reader_as_sen() -> None:
    gate = _load_i18n_gate()
    assert [where for where, value in _turkish_fields() if gate._SEN.search(value)] == []


def _doubled(short: re.Pattern[str]) -> re.Pattern[str]:
    """`edin` → `ediniz`, `okuyun` → `okuyunuz`: the doubled-polite form of
    every short imperative the INT-253 gate lists, derived from that list."""
    words = re.findall(r"[a-zçğıöşü]+", short.pattern.split("(?:", 1)[1].split(")", 1)[0])
    assert len(words) > 20
    forms = [w + re.findall(r"[ıiuü]", w)[-1] + "z" for w in words]
    return re.compile(r"(?i)\b(?:" + "|".join(forms) + r")\b")


def test_the_only_imperative_in_the_turkish_copy_is_the_static_safety_line() -> None:
    gate = _load_i18n_gate()
    doubled = _doubled(gate._SHORT_IMPERATIVE)
    offenders: list[tuple[str, str]] = []
    for where, value in _turkish_fields():
        for line in lines(value):
            if line == SAFETY_LINE_TR:
                continue
            if gate._SHORT_IMPERATIVE.search(line) or doubled.search(line):
                offenders.append((where, line))
    assert offenders == []
    assert gate._SHORT_IMPERATIVE.search(SAFETY_LINE_TR), "the near miss must be a real hit"
    assert doubled.search("Lütfen bu formu doldurup gönderiniz.")


# --- 5. the App Store fields the EAS reference states ------------------------------------------


def test_the_app_store_fields_hold_the_eas_reference_limits() -> None:
    assert (REPO / eas.EAS_REFERENCE).exists()
    for locale in LOCALES:
        fields = body(listing_source("app-store", locale))["fields"]
        assert set(fields) <= set(eas.INFO_COPY_FIELDS)
        for name, limit in eas.INFO_LIMITS.items():
            if name in fields:
                assert len(fields[name]) <= limit, (locale, name, len(fields[name]))
        assert ", " not in fields["keywords"]
        assert locale in eas.SUPPORTED_LOCALES


def test_no_link_is_authored_in_listing_copy(
    listings: tuple[listing_mod.StoreListing, ...], tmp_path: Path
) -> None:
    assert [
        x.path.name for x in listings if any(eas.URL.search(v) for v in x.fields.values())
    ] == []
    root = promote(tmp_path, stores=("app-store",))
    planted = root / "docs" / "legal" / "store" / "listing" / "app-store.tr.yaml"
    loaded = body(planted)
    loaded["fields"]["promoText"] = "Ayrıntılar: https://example.invalid/onvizit"
    planted.write_text(yaml.safe_dump(loaded, allow_unicode=True), encoding="utf-8")
    with pytest.raises(eas.StoreConfigError, match="link"):
        eas.render_for_repo(root)
