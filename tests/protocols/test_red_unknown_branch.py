"""INT-465 round 3: an unanswered location question can only ever go REMOTE.

files/04 §8.1 rule 7 and CD-24 (`generic_red_unknown_no_answer_goes_remote`): the
no-answer branch is the safe REMOTE action, never ON_SITE, because a guess that the
patient is already inside the hospital sends a patient at home nowhere. Every rule in
the repository says REMOTE. The type now says it too, at each boundary:
- the DSL (`UnknownAction.on_no_answer`);
- the served catalog (`QuestionOut.onNoAnswer`);
- the device decoder (apps/mobile/src/lib/red/hop.test.ts).
A document that says otherwise is refused, not coerced. The near miss is REMOTE, which
loads everywhere.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml
from intake_api.triage_rules import QuestionOut
from protocols.compile.life_threat import LifeThreatSetError, load_life_threat_set
from protocols.dsl import UnknownAction
from protocols.generic_red import GenericRedError, load_generic_red
from pydantic import ValidationError

REPO = Path(__file__).resolve().parents[2]
LIFE_THREAT = REPO / "files" / "protocols" / "base.life_threat.yaml"
GENERIC = REPO / "packages" / "protocols" / "generic" / "generic_red.yaml"
ASK = {"tr": "Şu anda hastanede misiniz?"}


def test_the_dsl_refuses_an_on_site_no_answer_branch() -> None:
    with pytest.raises(ValidationError):
        UnknownAction(ask_one_tr=ASK, on_yes="ON_SITE", on_no="REMOTE", on_no_answer="ON_SITE")
    # Near miss: REMOTE loads.
    loaded = UnknownAction(ask_one_tr=ASK, on_yes="ON_SITE", on_no="REMOTE", on_no_answer="REMOTE")
    assert loaded.on_no_answer == "REMOTE"


def test_the_served_catalog_refuses_an_on_site_no_answer_branch() -> None:
    with pytest.raises(ValidationError):
        QuestionOut(askTr="x", onYes="ON_SITE", onNo="REMOTE", onNoAnswer="ON_SITE")  # type: ignore[arg-type]
    assert (
        QuestionOut(askTr="x", onYes="ON_SITE", onNo="REMOTE", onNoAnswer="REMOTE").onNoAnswer
        == "REMOTE"
    )


def _write(tmp_path: Path, source: Path, edit: Any) -> Path:
    doc = copy.deepcopy(yaml.safe_load(source.read_text(encoding="utf-8")))
    edit(doc)
    path = tmp_path / source.name
    path.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def test_a_life_threat_rule_or_the_generic_with_an_on_site_no_answer_branch_is_refused(
    tmp_path: Path,
) -> None:
    def rule(doc: dict[str, Any]) -> None:
        doc["rules"][0]["action"]["UNKNOWN"]["on_no_answer"] = "ON_SITE"

    with pytest.raises(LifeThreatSetError):
        load_life_threat_set(_write(tmp_path, LIFE_THREAT, rule))

    def generic(doc: dict[str, Any]) -> None:
        doc["action"]["UNKNOWN"]["on_no_answer"] = "ON_SITE"

    with pytest.raises(GenericRedError):
        load_generic_red(_write(tmp_path, GENERIC, generic))
    # Near miss: the committed documents, both REMOTE, load.
    load_life_threat_set(LIFE_THREAT)
    load_generic_red(GENERIC)
