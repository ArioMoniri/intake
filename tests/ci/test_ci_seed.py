"""INT-544 — a job restores uv, pnpm and the deid model from its runner's cache seed.

Acceptance lines under test (docs/backlog/issues.yaml, INT-544):
  - the runners get a per-runner cache seed for uv, pnpm and the deid model,
    read-only to jobs, that works on self-hosted runners;
  - no secret or PHI in any cache; cache integrity is pinned by hash.

scripts/ci/ci_seed.sh is run here against seeds laid out exactly as
infra/ci/aws-runner/seed.sh builds them: a generation with a manifest of every
file, its sha256 recorded in SEED, and `current` pointing at it. A part that
fails any check is never copied, and the job falls back to the network.
"""

from __future__ import annotations

import hashlib
import io
import os
import subprocess
import tarfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "ci" / "ci_seed.sh"
TAG = "deid-tr-ner-v1"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _deid_tarball() -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        body = b'{"model_type": "synthetic-test"}\n'
        info = tarfile.TarInfo(f"{TAG}/config.json")
        info.size = len(body)
        tar.addfile(info, io.BytesIO(body))
    return buffer.getvalue()


def _write_manifest(gen: Path) -> None:
    lines = []
    for path in sorted(p for p in gen.rglob("*") if p.is_file() and not p.is_symlink()):
        rel = path.relative_to(gen).as_posix()
        if rel in {"MANIFEST.sha256", "SEED"}:
            continue
        lines.append(f"{_sha(path.read_bytes())}  ./{rel}\n")
    manifest = "".join(lines).encode()
    (gen / "MANIFEST.sha256").write_bytes(manifest)
    (gen / "SEED").write_text(f"inputs={'0' * 64}\nmanifest={_sha(manifest)}\nbuilt=test\n")


@pytest.fixture
def seed(tmp_path: Path) -> Path:
    """A seed as seed.sh lays it out, with one relative link as uv's cache has."""
    gen = tmp_path / "seed" / "gen-0000000000000000"
    (gen / "uv" / "archive-v0" / "abc").mkdir(parents=True)
    (gen / "uv" / "archive-v0" / "abc" / "METADATA").write_text("Name: example\n")
    (gen / "uv" / "wheels-v5").mkdir()
    (gen / "uv" / "wheels-v5" / "example").symlink_to("../archive-v0/abc")
    (gen / "pnpm-store" / "v3" / "files" / "00").mkdir(parents=True)
    (gen / "pnpm-store" / "v3" / "files" / "00" / "abcdef").write_text("module.exports = 1;\n")
    (gen / "deid").mkdir()
    (gen / "deid" / f"{TAG}.tar.gz").write_bytes(_deid_tarball())
    _write_manifest(gen)
    (tmp_path / "seed" / "current").symlink_to(gen.name)
    return tmp_path / "seed"


@pytest.fixture
def job(tmp_path: Path) -> Path:
    """A job's workspace whose Makefile pins the seed's deid asset."""
    work = tmp_path / "work"
    work.mkdir()
    (work / "Makefile").write_text(
        f"DEID_MODEL_TAG := {TAG}\nDEID_MODEL_SHA256 := {_sha(_deid_tarball())}\n"
    )
    (tmp_path / "temp").mkdir()
    return work


def _restore(job: Path, seed: Path | None, *parts: str) -> tuple[int, str, dict[str, str], str]:
    env = {
        "PATH": os.environ["PATH"],
        "RUNNER_TEMP": str(job.parent / "temp"),
        "GITHUB_ENV": str(job.parent / "github_env"),
        "GITHUB_OUTPUT": str(job.parent / "github_output"),
    }
    if seed is not None:
        env["INTAKE_CI_SEED"] = str(seed)
    for name in ("github_env", "github_output"):
        (job.parent / name).write_text("")
    result = subprocess.run(
        [str(SCRIPT), "restore", *parts], cwd=job, env=env, capture_output=True, text=True
    )
    outputs = dict(
        line.split("=", 1) for line in (job.parent / "github_output").read_text().splitlines()
    )
    return result.returncode, result.stdout, outputs, (job.parent / "github_env").read_text()


def test_every_part_is_restored_into_the_jobs_own_temp(seed: Path, job: Path) -> None:
    code, out, outputs, env = _restore(job, seed, "uv", "pnpm", "deid")
    assert code == 0, out
    assert outputs == {"uv": "true", "pnpm": "true", "deid": "true"}
    temp = job.parent / "temp"
    assert f"UV_CACHE_DIR={temp}/uv-cache\n" in env
    assert f"npm_config_store_dir={temp}/pnpm-store\n" in env
    link = temp / "uv-cache" / "wheels-v5" / "example"
    assert link.is_symlink() and (link / "METADATA").read_text() == "Name: example\n"
    assert (temp / "pnpm-store" / "v3" / "files" / "00" / "abcdef").is_file()
    assert (job / ".cache" / TAG / "config.json").is_file()
    # the job's copy is its own to write; the seed is never written
    (temp / "uv-cache" / "archive-v0" / "abc" / "METADATA").write_text("changed")
    assert (seed / "current" / "uv" / "archive-v0" / "abc" / "METADATA").read_text() == (
        "Name: example\n"
    )
    assert "manifest " in out


def test_a_runner_without_a_seed_uses_the_network(job: Path) -> None:
    code, out, outputs, env = _restore(job, None, "uv", "deid")
    assert code == 0
    assert outputs == {"uv": "false", "deid": "false"}
    assert env == "" and "no cache seed" in out


def test_a_changed_file_is_never_used(seed: Path, job: Path) -> None:
    (seed / "current" / "uv" / "archive-v0" / "abc" / "METADATA").write_text("Name: evil\n")
    code, out, outputs, env = _restore(job, seed, "uv", "pnpm")
    assert code == 0
    assert outputs == {"uv": "false", "pnpm": "true"}
    assert "UV_CACHE_DIR" not in env and not (job.parent / "temp" / "uv-cache").exists()
    assert "::warning title=cache seed::the uv part" in out


def test_an_added_file_is_never_used(seed: Path, job: Path) -> None:
    (seed / "current" / "pnpm-store" / "v3" / "files" / "00" / "extra").write_text("x")
    assert _restore(job, seed, "pnpm")[2] == {"pnpm": "false"}


def test_a_manifest_that_is_not_the_recorded_one_drops_the_whole_seed(
    seed: Path, job: Path
) -> None:
    manifest = seed / "current" / "MANIFEST.sha256"
    manifest.write_text(manifest.read_text() + f"{'0' * 64}  ./uv/forged\n")
    code, out, outputs, _ = _restore(job, seed, "uv", "pnpm", "deid")
    assert code == 0
    assert outputs == {"uv": "false", "pnpm": "false", "deid": "false"}
    assert "::warning title=cache seed::the seed's manifest" in out


def test_a_deid_asset_this_commit_does_not_pin_is_left_to_make_deid_model(
    seed: Path, job: Path
) -> None:
    (job / "Makefile").write_text(f"DEID_MODEL_TAG := {TAG}\nDEID_MODEL_SHA256 := {'1' * 64}\n")
    code, _, outputs, _ = _restore(job, seed, "deid", "uv")
    assert code == 0
    assert outputs == {"deid": "false", "uv": "true"}
    assert not (job / ".cache").exists()


def test_an_unknown_part_is_refused(seed: Path, job: Path) -> None:
    code, out, _, _ = _restore(job, seed, "uv", "docker")
    assert code == 2 and "unknown part 'docker'" in out


def test_the_seed_pins_the_deid_asset_the_makefile_pins() -> None:
    makefile = (REPO / "Makefile").read_text(encoding="utf-8")
    conf = (REPO / "infra" / "ci" / "aws-runner" / "runner.conf").read_text(encoding="utf-8")
    for make_key, conf_key in (
        ("DEID_MODEL_TAG", "SEED_DEID_TAG"),
        ("DEID_MODEL_SHA256", "SEED_DEID_SHA256"),
    ):
        make_value = next(
            line.split(":=", 1)[1].strip()
            for line in makefile.splitlines()
            if line.startswith(f"{make_key} :=")
        )
        conf_value = next(
            line.split("=", 1)[1].strip()
            for line in conf.splitlines()
            if line.startswith(f"{conf_key}=")
        )
        assert make_value == conf_value, make_key
