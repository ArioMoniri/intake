"""INT-453 / CD-24: the generic RED escalation document and its serve precondition.

The committed document carries CD-24's verified copy but stays
``draft_needs_source`` until the CD-24 register row is on main (#757), so it
refuses and nothing is served. The near miss is the SENTETİK test document,
which is servable. A document that claims more than it carries is refused at
load. ON_SITE can never offer 112, and the register policy can only be
CD-24's carry_engine_register.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from clinical_schemas.triage import RedLocation
from protocols.generic_red import (
    GENERIC_RED_DECISION,
    GENERIC_RED_SCRIPT_IDS,
    GenericRedError,
    generic_red_refusals,
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


def test_the_committed_document_holds_cd24s_copy_and_still_refuses() -> None:
    committed = load_generic_red(COMMITTED)
    assert committed.decision == GENERIC_RED_DECISION == "CD-24"
    assert committed.register_policy == "carry_engine_register"
    assert committed.action is not None
    assert committed.action.remote.action_tr == {"tr": "Hemen 112 Acil Çağrı Merkezi'ni arayın."}
    assert committed.action.on_site.show_112 is False
    assert committed.action.on_site.notify_staff_immediate is True
    assert committed.action.unknown.ask_one_tr == {"tr": "Şu anda hastanede misiniz?"}
    # Not servable until the CD-24 row is on main (#757): the precondition holds.
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
        lambda d: d.update(register_policy="always_alert"),  # the option CD-24 rejects
    ],
    ids=["no-source", "no-copy", "draft-no-gap", "on-site-112", "wrong-decision", "always-alert"],
)
def test_a_document_claiming_more_than_it_carries_is_refused(tmp_path: Path, edit: Any) -> None:
    with pytest.raises(GenericRedError):
        load_generic_red(_write(tmp_path, edit))


def test_one_generic_id_per_location() -> None:
    assert set(GENERIC_RED_SCRIPT_IDS) == set(RedLocation)
    assert len(set(GENERIC_RED_SCRIPT_IDS.values())) == len(RedLocation)
