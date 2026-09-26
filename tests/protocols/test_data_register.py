"""INT-349 — the data-category register loader refuses every shape that could
let an incomplete row pass for a complete one (invariant 18; owner decision D3).

Each case starts from the committed docs/legal/data-categories.yaml and breaks
exactly one thing, so a refusal here is a refusal of that one thing.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml
from protocols.data_register import (
    DATA_REGISTER_PATH,
    NO_REGISTER,
    DataRegisterError,
    load_data_register,
)
from protocols.types import DataCategory

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMITTED_REGISTER = REPO_ROOT / DATA_REGISTER_PATH

Mutation = Callable[[dict[str, Any]], Any]


def _committed() -> dict[str, Any]:
    raw: dict[str, Any] = yaml.safe_load(COMMITTED_REGISTER.read_text(encoding="utf-8"))
    return raw


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "data-categories.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def _mutated(tmp_path: Path, mutate: Mutation) -> Path:
    raw = _committed()
    mutate(raw)
    return _write(tmp_path, yaml.safe_dump(raw, allow_unicode=True, sort_keys=False))


MUTATIONS: dict[str, Mutation] = {
    "a_row_is_dropped": lambda raw: raw["categories"].pop(0),
    "a_row_is_duplicated": lambda raw: raw["categories"].append(dict(raw["categories"][0])),
    "general_health_gets_a_row": lambda raw: raw["categories"].append(
        {**raw["categories"][0], "category": "general_health"}
    ),
    "a_category_is_unknown": lambda raw: raw["categories"][0].update(category="sexual"),
    "a_counsel_key_is_left_out": lambda raw: raw["categories"][0].pop("basis"),
    "a_row_carries_an_extra_key": lambda raw: raw["categories"][0].update(guess="m.6"),
    "the_purpose_is_blank": lambda raw: raw["categories"][0].update(purpose="  "),
    "the_review_date_is_not_a_date": lambda raw: raw["categories"][0].update(
        counsel_reviewed_at="yakında"
    ),
    "the_version_is_missing": lambda raw: raw.pop("register_version"),
    "the_version_is_blank": lambda raw: raw.update(register_version=" "),
    "the_rows_are_not_a_list": lambda raw: raw.update(categories={"a": 1}),
    "an_unknown_top_level_key": lambda raw: raw.update(defaults={"basis": "m.6"}),
}


@pytest.mark.parametrize("name", sorted(MUTATIONS))
def test_the_loader_refuses_a_register_that_breaks_one_rule(tmp_path: Path, name: str) -> None:
    with pytest.raises(DataRegisterError):
        load_data_register(_mutated(tmp_path, MUTATIONS[name]))


def test_the_loader_refuses_a_missing_register_naming_int_349(tmp_path: Path) -> None:
    with pytest.raises(DataRegisterError, match="INT-349"):
        load_data_register(tmp_path / "absent.yaml")


def test_the_loader_refuses_text_that_is_not_yaml(tmp_path: Path) -> None:
    with pytest.raises(DataRegisterError, match="not valid YAML"):
        load_data_register(_write(tmp_path, "categories: [unclosed\n"))


def test_the_loader_refuses_a_register_that_is_not_a_mapping(tmp_path: Path) -> None:
    with pytest.raises(DataRegisterError, match="mapping"):
        load_data_register(_write(tmp_path, "- category: literacy\n"))


def test_the_absent_row_is_named_so_nobody_has_to_guess_which(tmp_path: Path) -> None:
    def drop_literacy(raw: dict[str, Any]) -> None:
        raw["categories"] = [r for r in raw["categories"] if r["category"] != "literacy"]

    with pytest.raises(DataRegisterError, match="no row for literacy"):
        load_data_register(_mutated(tmp_path, drop_literacy))


def test_control_a_row_counsel_has_completed_loads_and_reads_as_complete(tmp_path: Path) -> None:
    """The near-miss partner of every refusal above: a well-formed filled row is
    accepted, so the loader is a gate and not a wall. Synthetic values."""

    def complete_literacy(raw: dict[str, Any]) -> None:
        for row in raw["categories"]:
            if row["category"] == "literacy":
                row.update(
                    basis="SENTETİK dayanak — test verisi",
                    retention="SENTETİK saklama — test verisi",
                    recipients="SENTETİK alıcılar — test verisi",
                    consent_scope="sentetik_kapsam",
                    counsel_reviewed_at=date(2026, 9, 26),
                )

    register = load_data_register(_mutated(tmp_path, complete_literacy))
    assert register.missing(DataCategory.LITERACY) == ()
    assert register.missing(DataCategory.SEXUAL_HEALTH) != ()


def test_no_register_has_no_rows_so_every_tagged_category_is_missing_everything() -> None:
    for category in DataCategory:
        expected = () if category is DataCategory.GENERAL_HEALTH else ("the whole row",)
        assert NO_REGISTER.missing(category) == expected
