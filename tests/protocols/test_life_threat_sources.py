"""INT-465: a life-threat rule's source block is checked against its committed snapshot at load.

dsl.SourceBlock said the quote "must appear verbatim in a committed snapshot …
enforced by the compiler slice", and no such slice existed. The clinical review of
#796 found the committed exemplars citing:
- a URL the snapshot records as 404;
- a retrieval date the snapshot does not carry;
- quotes in lower case where EK-4 prints "Kardiyak …".

``load_life_threat_set`` now refuses any rule whose snapshot is missing or names
another guideline, whose quote is not verbatim (NFC and whitespace only), whose url
is neither the snapshot's ``url`` nor its ``url_annex``, or whose ``retrieved_on`` is
not the snapshot's. An ``active`` rule must cite a snapshot at all (CLAUDE.md clinical
content rules: "against a committed verbatim snapshot").

Every refusal has a near miss that loads.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml
from protocols.compile.life_threat import LifeThreatSetError, load_life_threat_set
from protocols.types import RuleStatus

REPO = Path(__file__).resolve().parents[2]
LIFE_THREAT = REPO / "files" / "protocols" / "base.life_threat.yaml"
SIGNED_FIXTURE = REPO / "tests" / "fixtures" / "protocols" / "compile" / "life_threat_signed.yaml"
CARDIAC = 0  # rf.chest_pain_cardiac_features, the first rule in the file


def _doc() -> dict[str, Any]:
    loaded = yaml.safe_load(LIFE_THREAT.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _write(tmp_path: Path, edit: Any) -> Path:
    doc = copy.deepcopy(_doc())
    edit(doc["rules"][CARDIAC]["evidence"])
    path = tmp_path / "base.life_threat.yaml"
    path.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def test_the_committed_set_loads_and_every_active_rule_cites_a_snapshot() -> None:
    life_threat = load_life_threat_set(LIFE_THREAT)
    active = [entry.rule for entry in life_threat.rules if entry.rule.status is RuleStatus.ACTIVE]
    assert active
    for rule in active:
        assert rule.source is not None and rule.source.quote_snapshot is not None, rule.id


def test_the_exemplar_sources_match_the_snapshot_header() -> None:
    """The fields the review found wrong, pinned to the snapshot's own header."""
    by_id = {e.rule.id: e.rule for e in load_life_threat_set(LIFE_THREAT).rules}
    for rule_id, quote in (
        ("rf.chest_pain_cardiac_features", "Kardiyak ağrıya benzer göğüs ağrısı"),
        ("rf.chest_pain_no_cardiac_history", "Kardiyak öykü ile uyumlu olmayan göğüs ağrısı"),
    ):
        source = by_id[rule_id].source
        assert source is not None
        assert source.quote == quote
        assert source.url == "https://www.resmigazete.gov.tr/eskiler/2022/09/20220913-5-1.pdf"
        assert source.retrieved_on.isoformat() == "2026-10-02"


@pytest.mark.parametrize(
    "edit",
    [
        lambda e: e.update(quote="kardiyak ağrıya benzer göğüs ağrısı"),  # case changed
        lambda e: e.update(quote="Kardiyak ağrıya benzeyen göğüs ağrısı"),  # one word changed
        lambda e: e.update(url="https://www.resmigazete.gov.tr/eskiler/2022/09/20220913-6.htm"),
        lambda e: e.update(retrieved_on="2026-08-25"),
        lambda e: e.update(quote_snapshot="packages/protocols/sources/ABSENT-2026.txt"),
        lambda e: e.update(quote_snapshot="packages/protocols/sources/NICE-NG232.txt"),
        lambda e: e.update(quote_snapshot="packages/protocols/sources/../sources/TR-EK4-2022.txt"),
        lambda e: e.pop("quote_snapshot"),
    ],
    ids=[
        "quote-case",
        "quote-word",
        "url-404",
        "retrieved-on",
        "snapshot-absent",
        "snapshot-other-guideline",
        "snapshot-path-escape",
        "active-without-snapshot",
    ],
)
def test_a_source_that_disagrees_with_its_snapshot_is_refused(tmp_path: Path, edit: Any) -> None:
    with pytest.raises(LifeThreatSetError):
        load_life_threat_set(_write(tmp_path, edit))


def test_the_snapshot_url_and_its_annex_url_are_both_accepted(tmp_path: Path) -> None:
    """Near miss for url-404: the Tebliğ body (url) and EK-4 (url_annex) are one snapshot."""
    for url in (
        "https://www.resmigazete.gov.tr/eskiler/2022/09/20220913-5.htm",
        "https://www.resmigazete.gov.tr/eskiler/2022/09/20220913-5-1.pdf",
    ):
        load_life_threat_set(_write(tmp_path, lambda e, url=url: e.update(url=url)))


def test_a_quote_wrapped_differently_is_still_verbatim(tmp_path: Path) -> None:
    """Near miss for quote-word: whitespace is the only normalisation."""
    load_life_threat_set(
        _write(tmp_path, lambda e: e.update(quote="Kardiyak  ağrıya\nbenzer göğüs ağrısı"))
    )


def test_a_draft_rule_without_a_snapshot_still_loads(tmp_path: Path) -> None:
    """Near miss for active-without-snapshot: a draft says what it waits for instead."""

    def draft(doc: dict[str, Any]) -> None:
        # A draft carries a source_gap and never a source block (files/04 §8.1 rule 3).
        rule = doc["rules"][CARDIAC]
        rule["status"] = "draft_needs_source"
        rule.pop("evidence")
        rule["source_gap"] = "sentetik: waiting for a committed snapshot"

    doc = copy.deepcopy(_doc())
    draft(doc)
    path = tmp_path / "base.life_threat.yaml"
    path.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    load_life_threat_set(path)


def test_the_synthetic_fixture_cites_a_committed_synthetic_snapshot() -> None:
    """The SENTETİK sets cite a snapshot under tests/fixtures, never packages/protocols/sources."""
    rule = load_life_threat_set(SIGNED_FIXTURE).rules[0].rule
    assert rule.source is not None and rule.source.quote_snapshot is not None
    assert rule.source.quote_snapshot.startswith("tests/fixtures/protocols/sources/")
