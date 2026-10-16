"""INT-496 — Google Play is deferred, and the deferral is a checklist, not a gap.

GitHub #847. The owner, 16 Oct 2026: *"dont do google for now"*. So no Play
submission is built. What is built is ``docs/store/google-play-later.md``: the
list of everything Play will need, each item pointing at the file or blocker
that owns it, so that the day Play is picked up nothing has to be rediscovered.

This suite holds three things:

- the list names every item #847 asks for;
- every repo path it cites exists, so the list cannot drift away from the
  artefacts it relies on;
- it makes no performance claim (invariant 20) and builds nothing: no Play
  service-account file, no Play submit step and no listing file appears in
  the tree because of it.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from intake_platform.legal import claims

REPO = Path(__file__).resolve().parents[2]
DOC = REPO / "docs" / "store" / "google-play-later.md"

#: #847's list, in its own words, with the phrase the document must carry.
REQUIRED = {
    "service-account JSON": "service-account JSON",
    "feature graphic": "feature graphic",
    "data-safety form from INT-482's derivation": "privacy-answers.draft.yaml",
    "IARC content rating": "IARC",
    "phone screenshots": "phone screenshots",
    "listing copy": "google-play.tr.draft.yaml",
    "reuse of the iOS assets (INT-495)": "INT-495",
}


def _text() -> str:
    return DOC.read_text(encoding="utf-8")


def test_the_play_list_names_everything_847_asks_for() -> None:
    text = _text()
    missing = [item for item, needle in REQUIRED.items() if needle not in text]
    assert missing == []
    assert "dont do google for now" in text


def test_every_cited_repo_path_exists() -> None:
    cited = set(re.findall(r"`((?:apps|docs|files|packages|scripts|tests)/[^`\s]+)`", _text()))
    assert cited, "the list cites no repo file"
    assert sorted(p for p in cited if not (REPO / p).exists()) == []


def test_every_vendor_figure_carries_its_source_and_date() -> None:
    """Play's limits are a vendor's published fact (HB-A12 spirit): each one
    quoted here names the help page and the day it was read."""
    text = _text()
    assert "support.google.com/googleplay/android-developer/answer/9866151" in text
    assert "support.google.com/googleplay/android-developer/answer/9859152" in text
    assert "retrieved 2026-10-16" in text


def test_the_list_claims_nothing_and_builds_nothing() -> None:
    assert claims.scan_text(_text(), groups=("performance", "satisfaction")) == ()
    tracked = subprocess.run(
        ["git", "ls-files", "--", "*service-account*", "*play-store-key*"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert tracked == [], "no Play service-account file may be tracked"
