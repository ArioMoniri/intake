"""INT-453 — the generic RED escalation document and its serve precondition.

The committed document is draft_needs_source until CD-24 (INT-432) lands, so
it refuses and nothing is served. The near miss is the SENTETİK test document,
which is servable. A document that claims more than it carries is refused at
load, and ON_SITE can never offer 112.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from clinical_schemas.triage import RedLocation, RedRegister
from protocols.generic_red import (
    DEFAULT_GENERIC_RED_REGISTER,
    GENERIC_RED_DECISION,
    GENERIC_RED_SCRIPT_IDS,
    GenericRedError,
    generic_red_refusals,
    generic_red_register,
    load_generic_red,
)

REPO = Path(__file__).resolve().parents[2]
COMMITTED = REPO / "packages" / "protocols" / "generic" / "generic_red.yaml"
SENTETIK = REPO / "tests" / "fixtures" / "triage_hop" / "generic_red_sentetik.yaml"


def _write(tmp_path: Path, edit: Any) -> Path:
    doc = yaml.safe_load(SENTETIK.read_text(encoding="utf-8"))
    edit(doc)
    path = tmp_path / "generic_red.yaml"
    path.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def test_the_committed_document_is_draft_cd24_and_refuses() -> None:
    committed = load_generic_red(COMMITTED)
    assert committed.decision == GENERIC_RED_DECISION == "CD-24"
    assert committed.action is None  # no copy: nothing invented
    assert generic_red_refusals(committed) == ("generic_red_draft_needs_source",)
    # Near miss: the servable SENTETİK document refuses nothing.
    assert generic_red_refusals(load_generic_red(SENTETIK)) == ()


def test_absent_refuses() -> None:
    assert generic_red_refusals(None) == ("generic_red_absent",)


def test_an_unreadable_document_raises(tmp_path: Path) -> None:
    with pytest.raises(GenericRedError):
        load_generic_red(tmp_path / "absent.yaml")


@pytest.mark.parametrize(
    "edit",
    [
        lambda d: d.pop("source"),  # active without its source
        lambda d: d.pop("action"),  # active without its copy
        lambda d: d.update(status="draft_needs_source"),  # draft without a source_gap
        lambda d: d["action"]["ON_SITE"].update(show_112=True),  # 112 under ON_SITE
        lambda d: d.update(decision="CD-99"),  # a copy no register row owns
    ],
    ids=["no-source", "no-copy", "draft-no-gap", "on-site-112", "wrong-decision"],
)
def test_a_document_claiming_more_than_it_carries_is_refused(tmp_path: Path, edit: Any) -> None:
    with pytest.raises(GenericRedError):
        load_generic_red(_write(tmp_path, edit))


def test_the_register_reads_cd24_once_servable_and_alert_until_then(tmp_path: Path) -> None:
    calm = load_generic_red(_write(tmp_path, lambda d: d.update(register="CALM")))
    assert generic_red_register(calm) is RedRegister.CALM
    # Near misses: the draft (even if it names a register) and absence keep ALERT.
    assert generic_red_register(load_generic_red(COMMITTED)) is DEFAULT_GENERIC_RED_REGISTER
    assert generic_red_register(None) is RedRegister.ALERT


def test_one_generic_id_per_location() -> None:
    assert set(GENERIC_RED_SCRIPT_IDS) == set(RedLocation)
    assert len(set(GENERIC_RED_SCRIPT_IDS.values())) == len(RedLocation)
