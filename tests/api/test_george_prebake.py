"""INT-443 — the pre-bake and the deploy probe of the George clip cache.

The bake fills exactly the cache the route reads, from exactly the catalogue
the route admits; it dials nothing in ``plan``, refuses an ``apply`` whose
misses would send more characters than the operator allowed, never bakes RED,
and names counts and lanes, never a text (invariant 6).
"""

from __future__ import annotations

import io
from pathlib import Path

from george_harness import CountingGateway, budget
from intake_api.dev_voice import GeorgeClipCache, GeorgeWiring
from intake_api.dev_voice_guard import CatalogueRow, catalogue_from_rows
from intake_api.george_prebake import main
from voice_clips.gateway import TtsUnavailableError

ROUTINE = "Şikâyetiniz ne zaman başladı?"
INSTRUMENT = "Son iki haftadır kendinizi nasıl hissediyorsunuz?"
RED = "Hemen yüz on ikiyi arayın."


def _wiring(tmp_path: Path, gateway: object) -> GeorgeWiring:
    catalogue = catalogue_from_rows(
        [
            CatalogueRow(ROUTINE, "routine"),
            CatalogueRow(INSTRUMENT, "instrument"),
            CatalogueRow(RED, "red"),
        ]
    )
    return GeorgeWiring(
        cache=GeorgeClipCache(gateway=gateway, cache_dir=tmp_path / "clips"),  # type: ignore[arg-type]
        catalogue=catalogue,
        budget=budget(),
    )


def _run(wiring: GeorgeWiring | None, *argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = main(list(argv), wiring_factory=lambda: wiring, stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


def test_plan_counts_and_dials_nothing(tmp_path: Path) -> None:
    gateway = CountingGateway()
    code, out, _ = _run(_wiring(tmp_path, gateway), "plan")
    assert code == 0
    assert "2 rows (1 red skipped), 0 cached, 2 to synthesise" in out
    assert f"{len(ROUTINE) + len(INSTRUMENT)} characters" in out
    assert gateway.calls == 0
    assert ROUTINE not in out and RED not in out


def test_apply_bakes_every_row_in_its_context_and_never_red(tmp_path: Path) -> None:
    gateway = CountingGateway()
    wiring = _wiring(tmp_path, gateway)
    code, out, _ = _run(wiring, "apply", "--max-characters", "1000")
    assert code == 0 and "elevenlabs=2" in out
    assert sorted(gateway.profiles) == ["delivery.instrument@v4", "delivery.routine@v4"]
    assert RED not in gateway.seen
    # a second run finds everything cached and sends nothing
    code, out, _ = _run(wiring, "apply", "--max-characters", "0")
    assert code == 0 and "2 cached, 0 to synthesise, 0 characters" in out
    assert gateway.calls == 2


def test_apply_refuses_a_spend_beyond_the_allowance(tmp_path: Path) -> None:
    gateway = CountingGateway()
    allowance = len(ROUTINE) + len(INSTRUMENT) - 1  # near miss: one character short
    code, _, err = _run(_wiring(tmp_path, gateway), "apply", "--max-characters", str(allowance))
    assert code == 3 and "refused" in err
    assert gateway.calls == 0


class _Down:
    def synthesise(self, **_: object) -> object:
        raise TtsUnavailableError("hosted_lane_unreachable")


def test_apply_reports_failures_by_class(tmp_path: Path) -> None:
    code, _, err = _run(_wiring(tmp_path, _Down()), "apply", "--max-characters", "1000")
    assert code == 1 and "TtsUnavailableError=2" in err


def test_probe_speaks_one_row_and_names_its_lane(tmp_path: Path) -> None:
    gateway = CountingGateway()
    wiring = _wiring(tmp_path, gateway)
    code, out, _ = _run(wiring, "probe")
    assert code == 0 and "lane=elevenlabs cache=miss" in out
    code, out, _ = _run(wiring, "probe")
    assert code == 0 and "lane=elevenlabs cache=hit" in out
    assert gateway.calls == 1


def test_an_unconfigured_host_is_exit_2(tmp_path: Path) -> None:
    code, _, err = _run(None, "probe")
    assert code == 2 and "unconfigured" in err
