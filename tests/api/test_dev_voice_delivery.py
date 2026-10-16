"""INT-414 — the dev George route admits the conversational delivery lines.

The route is catalogue-only (INT-326) and the delivery lines are app copy, not
pack content, so no compiled manifest carries them. ``with_delivery_lines``
widens a loaded catalogue by exactly those lines. What this suite holds:

- a delivery line is served, and reaches the vendor verbatim;
- free text is still refused before any dial, delivery lines or not;
- the widening never makes an EMPTY or unreadable manifest set look
  configured — the lane fails closed on exactly the conditions it did before;
- every manifest row is still admitted after the widening.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from george_harness import (
    CountingGateway,
    catalogue_of,
    compiled_dist,
    george_wiring_for,
    router_client,
    scripted_texts,
)
from intake_api.dev_voice import GEORGE_CLIP_PATH
from intake_api.dev_voice_delivery import DELIVERY_TR, delivery_text_hashes
from intake_api.dev_voice_guard import (
    ENV_APP_CATALOGUE,
    ENV_GEORGE_CLIP_DIST,
    load_scripted_catalogue,
    scripted_catalogue_from_env,
    with_delivery_lines,
)
from protocols.dsl import clip_text_hash

VOICE = "sentetik-ses"
_FREE_TEXT = "Göğsümde bir sıkışma var, bunu seslendirin"


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    return compiled_dist(tmp_path, voice=VOICE)


def test_every_delivery_line_is_admitted(tmp_path: Path) -> None:
    gateway = CountingGateway()
    wiring = george_wiring_for(
        gateway, tmp_path / "c", catalogue=with_delivery_lines(catalogue_of("Şikayetiniz nedir?"))
    )
    client = router_client(wiring)
    for text in DELIVERY_TR.values():
        response = client.post(GEORGE_CLIP_PATH, json={"text_tr": text})
        assert response.status_code == 200, text
    assert gateway.seen == list(DELIVERY_TR.values())


def test_a_delivery_line_is_never_served_as_red(tmp_path: Path) -> None:
    # RED gets nothing around it (invariant 21): no delivery line may be
    # fetched under the red label, and the route's INT-415 door says so.
    gateway = CountingGateway()
    wiring = george_wiring_for(
        gateway, tmp_path / "c", catalogue=with_delivery_lines(catalogue_of())
    )
    for text in DELIVERY_TR.values():
        response = router_client(wiring).post(
            GEORGE_CLIP_PATH, json={"text_tr": text, "delivery_context": "red"}
        )
        assert response.status_code == 422, text
        assert response.json() == {"error": "red_not_on_demand"}
    assert gateway.calls == 0


@pytest.mark.parametrize(
    "context", ["welcome", "routine", "sensitive", "instrument", "acknowledgement", "closing"]
)
def test_a_delivery_line_carries_no_pin_so_every_other_context_admits_it(
    tmp_path: Path, context: str
) -> None:
    gateway = CountingGateway()
    wiring = george_wiring_for(
        gateway, tmp_path / "c", catalogue=with_delivery_lines(catalogue_of())
    )
    line = next(iter(DELIVERY_TR.values()))
    assert wiring.catalogue.pinned_context(line) is None
    response = router_client(wiring).post(
        GEORGE_CLIP_PATH, json={"text_tr": line, "delivery_context": context}
    )
    assert response.status_code == 200
    assert gateway.seen == [line]


def test_free_text_is_still_refused_and_never_dialled(tmp_path: Path) -> None:
    gateway = CountingGateway()
    wiring = george_wiring_for(
        gateway, tmp_path / "c", catalogue=with_delivery_lines(catalogue_of())
    )
    response = router_client(wiring).post(GEORGE_CLIP_PATH, json={"text_tr": _FREE_TEXT})
    assert response.status_code == 422
    assert response.json() == {"error": "not_in_catalogue"}
    assert _FREE_TEXT not in response.text
    assert gateway.calls == 0


def test_a_near_miss_of_a_delivery_line_is_refused(tmp_path: Path) -> None:
    gateway = CountingGateway()
    wiring = george_wiring_for(
        gateway, tmp_path / "c", catalogue=with_delivery_lines(catalogue_of())
    )
    line = next(iter(DELIVERY_TR.values()))
    for near in (f"{line} ", line.rstrip("."), line.upper()):
        response = router_client(wiring).post(GEORGE_CLIP_PATH, json={"text_tr": near})
        assert response.status_code == 422, near
    assert gateway.calls == 0


def test_the_widening_keeps_every_manifest_row(dist: Path) -> None:
    loaded = load_scripted_catalogue(dist)
    widened = with_delivery_lines(loaded)
    assert loaded.text_hashes <= widened.text_hashes
    assert widened.text_hashes == loaded.text_hashes | delivery_text_hashes()
    for text in scripted_texts(dist):
        assert widened.admits(text)


def test_the_env_catalogue_carries_the_delivery_lines(
    monkeypatch: pytest.MonkeyPatch, dist: Path
) -> None:
    monkeypatch.setenv(ENV_GEORGE_CLIP_DIST, str(dist))
    catalogue = scripted_catalogue_from_env()
    assert catalogue is not None
    for text in DELIVERY_TR.values():
        assert clip_text_hash(text) in catalogue.text_hashes


def test_delivery_lines_never_make_an_empty_manifest_set_configured(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    empty = tmp_path / "dist"
    empty.mkdir()
    monkeypatch.setenv(ENV_GEORGE_CLIP_DIST, str(empty))
    # INT-443 admits the app's catalogue beside the manifests; with neither,
    # the delivery lines alone must still leave the lane unconfigured
    monkeypatch.setenv(ENV_APP_CATALOGUE, str(tmp_path / "no-app-catalogue.json"))
    assert scripted_catalogue_from_env() is None
