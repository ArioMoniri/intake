"""INT-347 — the object store runs one owner-approved, digest-pinned image.

MinIO, Inc. withdrew its community distribution: the server and client images
it published under its own Docker Hub and quay.io namespaces no longer pull,
so ``check-integration`` stopped at ``compose up`` (INT-346 §4, F9). The owner
chose the maintained AGPL community fork, published as ``pgsty/minio``, pinned
by sha256 digest (chat, 2026-09-26). That image ships the ``mc`` client as
well, so the backup toolbox runs the same bytes and there is one pin, not two.

One source of truth: the ``minio`` row of ``observability/registry.yaml``. Its
typed ``image`` field holds the approved reference, ``<repo>:<release
tag>@sha256:<index digest>``, and the same row records the licence as read
from the raw LICENSE blob at a pinned revision (CLAUDE.md invariants 14 and
19). The digest is not in ``host``: the console serves ``host``, and
``tests/admin/test_admin_audit.py`` forbids any 64-hex string in an admin
response. Every compose service that runs the object store or its client, and
every other textual reference to the fork anywhere in the tree, must equal the
``image`` reference byte for byte. A digest change is therefore one edit to the
registry plus the compose files this test names, never a silent drift in one
of them.

Guards that assert a name is absent never spell that name, so this file cannot
trip its own scan (the withdrawn repositories are assembled from parts).
"""

from __future__ import annotations

import re
import subprocess
from functools import cache
from pathlib import Path
from typing import Any

import pytest
import yaml
from intake_probes.registry import RegistryEntry, load_registry
from pydantic import ValidationError

REPO = Path(__file__).resolve().parents[2]
INFRA = REPO / "infra"
REGISTRY = REPO / "observability" / "registry.yaml"
OBJECT_STORE_COMPONENT = "minio"

#: The owner-approved fork's repository (chat, 2026-09-26).
APPROVED_REPOSITORY = "pgsty/minio"

#: ``<repo>:<RELEASE tag>@sha256:<64 hex>`` — the tag is for the reader, the
#: digest is what the runtime resolves. A tag alone can be repointed.
APPROVED_SHAPE = re.compile(
    rf"^{re.escape(APPROVED_REPOSITORY)}"
    r":RELEASE\.\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z@sha256:[0-9a-f]{64}$"
)

#: An image reference stops at whitespace, a quote, a backtick or a closing
#: bracket. The look-behind skips URLs (``github.com/<org>/<repo>``), which
#: name source repositories rather than images.
_REF_TAIL = r"[^\s\"'`,)\]]*"
_NOT_IN_A_URL = r"(?<![\w./-])"
#: In free text a repository name counts as an image reference when a tag or
#: digest follows it; a bare name in a sentence is prose. An untagged
#: ``image:`` in a compose file is caught structurally, by the compose scan.
_IS_A_REFERENCE = rf"[:@]{_REF_TAIL}"

#: Every object-store service the tree runs: (compose file, service). A new
#: one joins this set deliberately, or the scan below is not exhaustive.
EXPECTED_OBJECT_STORE_SERVICES = {
    ("infra/docker-compose.dev.yml", "minio"),
    ("infra/docker-compose.langfuse.yml", "langfuse-minio"),
    ("infra/docker-compose.backup.yml", "minio-dr"),
    ("infra/docker-compose.backup.yml", "mc"),
}

#: Dated records of what happened before this change. They quote the old
#: reference as history, not as configuration.
HISTORICAL_PREFIXES = ("docs/evidence/",)


def _withdrawn_pattern() -> re.Pattern[str]:
    vendor = "min" + "io"
    repos = "|".join((vendor, "mc"))
    hub = rf"{_NOT_IN_A_URL}(?:docker\.io/)?{vendor}/(?:{repos})(?![\w-])"
    quay = rf"quay\.io/{vendor}/"
    return re.compile(f"{hub}|{quay}")


def _fork_reference_pattern() -> re.Pattern[str]:
    owner, _, name = APPROVED_REPOSITORY.partition("/")
    return re.compile(rf"{_NOT_IN_A_URL}{owner}/(?:{name}|mc){_IS_A_REFERENCE}")


@cache
def _registry_row() -> RegistryEntry:
    return load_registry(REGISTRY).get(OBJECT_STORE_COMPONENT)


def _approved_reference() -> str:
    image = _registry_row().image
    assert image is not None, (
        f"the {OBJECT_STORE_COMPONENT!r} registry row must pin its image in `image`"
    )
    return image


@cache
def _tracked_text_files() -> tuple[tuple[str, str], ...]:
    listed = subprocess.run(
        ["git", "ls-files", "-z"], cwd=REPO, capture_output=True, check=True
    ).stdout.decode("utf-8")
    out: list[tuple[str, str]] = []
    for rel in filter(None, listed.split("\0")):
        if rel.startswith(HISTORICAL_PREFIXES):
            continue
        path = REPO / rel
        if not path.is_file():
            continue
        try:
            out.append((rel, path.read_text(encoding="utf-8")))
        except UnicodeDecodeError:
            continue
    return tuple(out)


def _compose_files() -> list[Path]:
    names = ("compose.yaml", "compose.yml")
    return sorted(
        p
        for p in INFRA.rglob("*")
        if p.is_file() and (p.name.startswith("docker-compose") or p.name in names)
    )


def _repository(ref: str) -> str:
    name = ref.split("@", 1)[0]
    head, sep, tail = name.rpartition(":")
    return head if sep and "/" not in tail else name


def _object_store_services() -> dict[tuple[str, str], str]:
    found: dict[tuple[str, str], str] = {}
    for path in _compose_files():
        loaded: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            continue
        for name, service in (loaded.get("services") or {}).items():
            image = str((service or {}).get("image", ""))
            if _repository(image).rsplit("/", 1)[-1] in {"minio", "mc"}:
                found[(str(path.relative_to(REPO)), str(name))] = image
    return found


# --- the one source of truth ------------------------------------------------------------


def _row(**overrides: Any) -> RegistryEntry:
    base: dict[str, Any] = {
        "component": "object-store",
        "self_hostable": True,
        "self_hosted_now": True,
        "host": "dev compose 127.0.0.1:9000",
        "license": "AGPL-3.0-only",
        "probe": "minio_ready",
        "budget_ms": 1000,
        "fallback": "none",
        "phi_path": True,
    }
    return RegistryEntry.model_validate({**base, **overrides})


_VERIFIED = {
    "licence_verified_at": "2026-09-26",
    "licence_blob_url": "https://raw.githubusercontent.com/example/repo/" + "c" * 40 + "/LICENSE",
    "licence_blob_sha256": "d" * 64,
}


class TestTheRegistrySchemaPinsImagesByDigest:
    def test_a_digest_pinned_image_with_a_verified_licence_loads(self) -> None:
        ref = f"{APPROVED_REPOSITORY}:RELEASE.2026-08-04T00-00-00Z@sha256:{'e' * 64}"
        assert _row(image=ref, **_VERIFIED).image == ref

    def test_a_tag_without_a_digest_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            _row(image=f"{APPROVED_REPOSITORY}:RELEASE.2026-08-04T00-00-00Z", **_VERIFIED)

    def test_a_digest_without_the_readable_tag_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            _row(image=f"{APPROVED_REPOSITORY}@sha256:{'e' * 64}", **_VERIFIED)

    def test_a_short_digest_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            _row(image=f"{APPROVED_REPOSITORY}:RELEASE.x@sha256:{'e' * 12}", **_VERIFIED)

    def test_an_image_pin_without_a_dated_licence_verification_is_refused(self) -> None:
        ref = f"{APPROVED_REPOSITORY}:RELEASE.2026-08-04T00-00-00Z@sha256:{'e' * 64}"
        with pytest.raises(ValidationError, match="invariants 14 and 19"):
            _row(image=ref)


class TestTheRegistryRowIsTheSourceOfTruth:
    def test_it_names_one_reference_pinned_by_release_tag_and_sha256_digest(self) -> None:
        ref = _approved_reference()
        assert APPROVED_SHAPE.fullmatch(ref), (
            f"{ref!r} is not `{APPROVED_REPOSITORY}:RELEASE.<ts>@sha256:<64 hex>` — "
            "an image is pinned by digest (CLAUDE.md invariant 14)"
        )

    def test_the_served_host_names_the_release_but_never_carries_the_digest(self) -> None:
        row = _registry_row()
        tag = _approved_reference().split("@", 1)[0].rpartition(":")[2]
        assert f"{APPROVED_REPOSITORY} {tag}" in row.host, (
            f"`host` should name {APPROVED_REPOSITORY} {tag} for the console reader"
        )
        assert not re.search(r"\b[0-9a-f]{64}\b", row.host), (
            "the console serves `host`; no admin response may carry a 64-hex string"
        )

    def test_it_records_the_licence_read_from_the_raw_blob_at_a_pinned_revision(self) -> None:
        row = _registry_row()
        assert row.license == "AGPL-3.0-only"
        assert row.licence_verified_at is not None, (
            "invariant 19: the licence is verified from the raw LICENSE blob and dated"
        )
        assert row.licence_blob_url is not None
        assert re.fullmatch(
            r"https://raw\.githubusercontent\.com/pgsty/[\w.-]+/[0-9a-f]{40}/LICENSE",
            row.licence_blob_url,
        ), f"{row.licence_blob_url} is not a raw blob at a full 40-hex revision"
        assert row.licence_blob_sha256 is not None
        assert row.licence_note is not None
        assert "owner chose pgsty/minio (chat, 2026-09-26)" in row.licence_note

    def test_the_object_store_stays_on_the_phi_path_and_self_hostable(self) -> None:
        row = _registry_row()
        assert row.phi_path and row.self_hostable and row.self_hosted_now


# --- nothing pulls the withdrawn images -------------------------------------------------


class TestTheWithdrawnImagesAreGone:
    def test_the_scan_recognises_what_it_forbids(self) -> None:
        pattern = _withdrawn_pattern()
        vendor = "min" + "io"
        for positive in (
            f"image: {vendor}/{vendor}:RELEASE.2024-01-16T16-07-38Z",
            f"image: {vendor}/mc:RELEASE.2024-11-21T17-21-54Z",
            f'"host": "dev compose — {vendor}/{vendor}:RELEASE.x"',
            f"image: docker.io/{vendor}/{vendor}",
            f"image: quay.io/{vendor}/{vendor}:latest",
        ):
            assert pattern.search(positive), positive
        for negative in (
            f"image: {APPROVED_REPOSITORY}:RELEASE.2026-08-04T00-00-00Z",
            f"https://raw.githubusercontent.com/{vendor}/{vendor}/master/LICENSE",
            f"https://github.com/{vendor}/{vendor}",
            f"infra/backup/{vendor}-replication.yaml",
            f"{vendor}/health/ready",
        ):
            assert not pattern.search(negative), negative

    def test_no_tracked_file_references_a_withdrawn_image(self) -> None:
        pattern = _withdrawn_pattern()
        hits = [
            f"{rel}:{lineno}: {line.strip()}"
            for rel, text in _tracked_text_files()
            for lineno, line in enumerate(text.splitlines(), start=1)
            if pattern.search(line)
        ]
        assert not hits, "withdrawn object-store image still referenced:\n" + "\n".join(hits)


# --- every reference agrees with the source of truth ------------------------------------


class TestEveryReferenceIsTheApprovedOne:
    def test_the_reference_scan_tells_a_pull_from_prose(self) -> None:
        pattern = _fork_reference_pattern()
        repo = APPROVED_REPOSITORY
        owner = repo.split("/", 1)[0]
        pinned = f"{repo}:RELEASE.2026-08-04T00-00-00Z@sha256:{'a' * 64}"
        assert pattern.findall(f"    image: {pinned}") == [pinned]
        assert pattern.findall(f'"host": "dev compose — {pinned}",') == [pinned]
        assert pattern.findall(f"image: {repo}@sha256:{'b' * 64}") == [f"{repo}@sha256:{'b' * 64}"]
        assert pattern.findall(f"image: {owner}/mc:RELEASE.x") == [f"{owner}/mc:RELEASE.x"]
        assert not pattern.findall(f"the owner chose {repo} (chat, 2026-09-26)")
        assert not pattern.findall(f"https://github.com/{repo}/releases")

    def test_the_compose_scan_finds_exactly_the_known_object_store_services(self) -> None:
        assert set(_object_store_services()) == EXPECTED_OBJECT_STORE_SERVICES

    def test_every_object_store_service_runs_the_approved_reference(self) -> None:
        approved = _approved_reference()
        drift = {key: image for key, image in _object_store_services().items() if image != approved}
        assert not drift, f"not the approved {approved!r}: {drift}"

    def test_the_client_toolbox_runs_the_same_image_through_a_shell(self) -> None:
        compose = yaml.safe_load((INFRA / "docker-compose.backup.yml").read_text("utf-8"))
        mc = compose["services"]["mc"]
        assert mc["image"] == _approved_reference()
        assert mc["entrypoint"] == ["/bin/sh"], "replication commands are piped to a shell"

    def test_every_textual_reference_to_the_fork_is_the_approved_one(self) -> None:
        approved = _approved_reference()
        pattern = _fork_reference_pattern()
        seen: set[str] = set()
        drift: list[str] = []
        for rel, text in _tracked_text_files():
            for ref in pattern.findall(text):
                seen.add(rel)
                if ref != approved:
                    drift.append(f"{rel}: {ref}")
        assert not drift, f"every reference must be {approved!r}:\n" + "\n".join(drift)
        for rel, _service in EXPECTED_OBJECT_STORE_SERVICES:
            assert rel in seen
        assert "observability/registry.yaml" in seen
