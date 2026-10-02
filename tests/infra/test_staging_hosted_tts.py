"""INT-443 — the synthetic host's hosted TTS, as the staging artefacts declare it.

ElevenLabs is the synthetic deployment's default TTS for scripted clips: the
compose declares the lane and its persistent cache, the image creates the
cache's mount point for the service user and ships the app's catalogue (and
nothing else of ``apps/``), and every deploy's smoke speaks one clip and names
its lane. The lane name is set nowhere else in the tree, so no PHI deployment
declares it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from intake_api.dev_voice_guard import APP_CATALOGUE_DEFAULT, ENV_HOSTED_TTS
from intake_api.hosted_clip_lane import ENV_HOSTED_TTS_CACHE_DIR

REPO = Path(__file__).resolve().parents[2]
STAGING = REPO / "infra" / "staging"
CACHE_DIR = "/var/lib/intake/george-clips"


def _api() -> dict[str, Any]:
    compose: dict[str, Any] = yaml.safe_load((STAGING / "compose.yaml").read_text(encoding="utf-8"))
    api: dict[str, Any] = compose["services"]["api"]
    assert "george-clips" in compose["volumes"]
    return api


def test_the_api_declares_the_lane_and_its_persistent_cache() -> None:
    api = _api()
    assert api["environment"][ENV_HOSTED_TTS] == "elevenlabs"
    assert api["environment"][ENV_HOSTED_TTS_CACHE_DIR] == CACHE_DIR
    assert api["volumes"] == [f"george-clips:{CACHE_DIR}"]
    assert api["read_only"] is True, "the volume is the one writable path"
    assert not any(k.startswith("INTAKE_DEV_") for k in api["environment"])


def test_the_image_creates_the_mount_point_for_the_service_user_only() -> None:
    dockerfile = (STAGING / "Dockerfile.api").read_text(encoding="utf-8")
    assert f"install -d -o 10001 -g 10001 -m 0750 {CACHE_DIR}" in dockerfile


def test_the_image_ships_the_app_catalogue_and_nothing_else_of_apps() -> None:
    ignore = (STAGING / "Dockerfile.api.dockerignore").read_text(encoding="utf-8").splitlines()
    included = [line for line in ignore if line.startswith("!apps")]
    assert included == [f"!{APP_CATALOGUE_DEFAULT}"]
    assert (REPO / APP_CATALOGUE_DEFAULT).is_file()


def test_every_deploy_speaks_one_clip_and_names_its_lane() -> None:
    smoke = (STAGING / "smoke.sh").read_text(encoding="utf-8")
    assert "python -m intake_api.george_prebake probe" in smoke


def test_the_lane_is_declared_by_the_synthetic_compose_and_nothing_else() -> None:
    setters = []
    for root in ("infra", ".github"):
        for path in (REPO / root).rglob("*"):
            if not path.is_file() or path.suffix in {".py", ".md"}:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if ENV_HOSTED_TTS in text:
                setters.append(path.relative_to(REPO).as_posix())
    env_example = (REPO / "env.example").read_text(encoding="utf-8")
    assert sorted(setters) == ["infra/staging/compose.yaml"]
    assert ENV_HOSTED_TTS not in env_example
