"""INT-599: the admin-web runtime image carries the console's built output and the
packages its server runs, and none of the build or developer tooling.

Before INT-599, infra/staging/Dockerfile.admin-web installed the workspace root's
devDependencies alongside admin-web's own in its builder, and its runtime stage copied
the builder's /app whole. So eslint, typescript, vitest, prettier, commitlint, jsdom and
the rest shipped in the image the staging host runs, while the osv/trivy exception
reasons for zod and deepmerge said that no server runtime image installs npm packages.

No container runtime exists where this suite runs (tests/infra/test_staging_compose.py
says why), so nothing here builds the image. What is decidable without building it:

- the runtime stage copies two things out of the builder: Next's standalone output and
  its static assets. Nothing comes from the build context, and the one command it runs
  removes the package managers the node base image ships (npm with its bundled
  packages, npx, corepack and Yarn 1), so no package manager is left to run there;
- next.config.ts asks Next for that standalone output, and the server is its server.js;
- the builder installs exactly admin-web's closure and the workspace root. Walked over
  pnpm-lock.yaml with devDependencies included, that closure holds no Expo package, no
  zod 3.25.76 and no deepmerge. The runtime stage can carry only part of what the
  builder installed, so it cannot carry those either. The control: the same walk from
  apps/mobile finds all three;
- the standalone trace is bounded by admin-web's production closure where that can be
  decided, inside the builder: after `next build`, admin_web_trace_guard.sh fails the
  image build when any package file in the trace lies outside the store entries pnpm
  lists for that closure. The guard runs here over fixture trees, with near misses, and
  the production closure itself is shown to hold no devDependency.

The image build on the AWS host is the end-to-end check. It is recorded in
docs/evidence/INT-599.md when it runs; nothing here claims it ran.
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
STAGING = REPO / "infra" / "staging"
DOCKERFILE = STAGING / "Dockerfile.admin-web"
DOCKERIGNORE = STAGING / "Dockerfile.admin-web.dockerignore"
GUARD = STAGING / "admin_web_trace_guard.sh"
COMPOSE = STAGING / "compose.yaml"
ADMIN_WEB = REPO / "apps" / "admin-web"
NEXT_CONFIG = ADMIN_WEB / "next.config.ts"
LOCKFILE = REPO / "pnpm-lock.yaml"

APP = "/app/apps/admin-web"
STANDALONE = f"{APP}/.next/standalone"
STATIC = f"{APP}/.next/static"
#: Everything the runtime stage may copy, as (stage, source, destination).
RUNTIME_COPIES = [("builder", STANDALONE, "/app"), ("builder", STATIC, STATIC)]
#: The package managers the node base image ships: npm (with the packages it bundles),
#: npx, corepack and Yarn 1. The runtime stage's one command removes them; `rm -r`
#: without -f fails the build if a new base image moves one.
BASE_TOOLING = [
    "/usr/local/lib/node_modules",
    "/opt/yarn-v${YARN_VERSION}",
    "/usr/local/bin/npm",
    "/usr/local/bin/npx",
    "/usr/local/bin/corepack",
    "/usr/local/bin/yarn",
    "/usr/local/bin/yarnpkg",
]
PRUNE = ["rm", "-r", *BASE_TOOLING]
#: The guard reads the trace from the builder's working directory, /app.
TRACE = "apps/admin-web/.next/standalone"
GUARD_IN_CONTEXT = "infra/staging/admin_web_trace_guard.sh"
BUILDER_FILTERS = ["@intake/admin-web...", "intake"]
PRODUCTION_LIST = 'pnpm --filter "@intake/admin-web..." list --prod --parseable --depth Infinity'

ALL_KINDS = ("dependencies", "devDependencies", "optionalDependencies")
PRODUCTION_KINDS = ("dependencies", "optionalDependencies")
#: (name, version); None means every version. The exception reasons INT-599 corrects.
NAMED = (("@expo/cli", None), ("zod", "3.25.76"), ("deepmerge", None))


# --- reading the Dockerfile ----------------------------------------------------------------


@dataclass
class Stage:
    base: str
    name: str | None
    instructions: list[tuple[str, str]] = field(default_factory=list)


def _instructions(text: str) -> list[tuple[str, str]]:
    """(INSTRUCTION, arguments) with continuations joined and comments dropped."""
    joined: list[str] = []
    buffer = ""
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.endswith("\\"):
            buffer += stripped[:-1] + " "
            continue
        joined.append(buffer + stripped)
        buffer = ""
    out = []
    for statement in joined:
        head, _, rest = statement.partition(" ")
        out.append((head.upper(), rest.strip()))
    return out


def _stages(text: str) -> list[Stage]:
    stages: list[Stage] = []
    for keyword, args in _instructions(text):
        if keyword == "FROM":
            parts = [p for p in args.split() if not p.startswith("--")]
            name = parts[2] if len(parts) >= 3 and parts[1].lower() == "as" else None
            stages.append(Stage(parts[0], name))
        else:
            stages[-1].instructions.append((keyword, args))
    return stages


def _copies(stage: Stage) -> list[tuple[str | None, str, str]]:
    """(--from stage, or None for the build context, source, destination) per COPY/ADD."""
    out: list[tuple[str | None, str, str]] = []
    for keyword, args in stage.instructions:
        if keyword not in {"COPY", "ADD"}:
            continue
        tokens = shlex.split(args)
        flags = [t for t in tokens if t.startswith("--")]
        paths = [t for t in tokens if not t.startswith("--")]
        origin = next((f.split("=", 1)[1] for f in flags if f.startswith("--from=")), None)
        for source in paths[:-1]:
            out.append((origin if keyword == "COPY" else f"ADD:{origin}", source, paths[-1]))
    return out


def _runtime_violations(text: str) -> list[str]:
    """Every way the final stage could carry something other than the build output."""
    runtime = _stages(text)[-1]
    problems = [f"{k} {a}" for k, a in runtime.instructions if k in {"ADD", "ONBUILD"}]
    runs = [shlex.split(a) for k, a in runtime.instructions if k == "RUN"]
    if runs != [PRUNE]:
        problems.append(f"runs {runs}, expected only {PRUNE}")
    copies = _copies(runtime)
    problems += [f"COPY {src} -> {dst} from the build context" for o, src, dst in copies if not o]
    if copies != RUNTIME_COPIES:
        problems.append(f"copies {copies}, expected {RUNTIME_COPIES}")
    return problems


def _entry_point(text: str) -> tuple[str, list[str]]:
    """The runtime stage's last WORKDIR and its CMD argv."""
    runtime = dict(_stages(text)[-1].instructions)
    return runtime["WORKDIR"], json.loads(runtime["CMD"])


def _text() -> str:
    return DOCKERFILE.read_text(encoding="utf-8")


def _builder_run() -> str:
    (builder,) = [s for s in _stages(_text()) if s.name == "builder"]
    runs = [a for k, a in builder.instructions if k == "RUN"]
    assert len(runs) == 1, "the builder installs, builds and guards in one RUN"
    return runs[0]


def _install_filters(run: str) -> list[str]:
    commands = [c.strip() for c in run.split("&&")]
    (install,) = [shlex.split(c) for c in commands if c.startswith("pnpm install")]
    return [install[i + 1] for i, token in enumerate(install) if token == "--filter"]


# --- walking pnpm-lock.yaml ------------------------------------------------------------------


def _lock() -> dict[str, Any]:
    loaded = yaml.safe_load(LOCKFILE.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _importer_names(lock: dict[str, Any]) -> dict[str, str]:
    """package name -> importer directory, for every workspace project."""
    names = {}
    for importer in lock["importers"]:
        manifest = json.loads((REPO / importer / "package.json").read_text(encoding="utf-8"))
        names[manifest["name"]] = importer
    return names


def _importers_for(lock: dict[str, Any], filters: Iterable[str]) -> set[str]:
    """The importers a `pnpm install --filter` selection names (`X...` adds X's own
    workspace dependencies, of every kind, transitively)."""
    names = _importer_names(lock)
    selected: set[str] = set()
    for selector in filters:
        with_deps = selector.endswith("...")
        stack = [names[selector.removesuffix("...")]]
        while stack:
            importer = stack.pop()
            if importer in selected:
                continue
            selected.add(importer)
            if not with_deps:
                continue
            for kind in ALL_KINDS:
                for dep in (lock["importers"][importer].get(kind) or {}).values():
                    if str(dep["version"]).startswith("link:"):
                        target = (REPO / importer / dep["version"][5:]).resolve()
                        stack.append(target.relative_to(REPO).as_posix())
    return selected


def _closure(
    lock: dict[str, Any], importers: Iterable[str], kinds: tuple[str, ...]
) -> set[tuple[str, str]]:
    """(name, version) of every package those importers' `kinds` reach, transitively."""
    snapshots = lock["snapshots"]
    stack: list[str] = []
    for importer in importers:
        for kind in kinds:
            for name, dep in (lock["importers"][importer].get(kind) or {}).items():
                if not str(dep["version"]).startswith("link:"):
                    stack.append(f"{name}@{dep['version']}")
    seen: set[str] = set()
    while stack:
        key = stack.pop()
        if key in seen:
            continue
        seen.add(key)
        snapshot = snapshots[key] or {}
        for kind in ("dependencies", "optionalDependencies"):
            for name, version in (snapshot.get(kind) or {}).items():
                if not str(version).startswith("link:"):
                    stack.append(f"{name}@{version}")
    out = set()
    for key in seen:
        bare = key.split("(", 1)[0]
        at = bare.rindex("@")
        out.add((bare[:at], bare[at + 1 :]))
    return out


def _named_in(packages: set[tuple[str, str]]) -> list[str]:
    hits = [
        f"{name}@{version}"
        for name, version in sorted(packages)
        for want, pinned in NAMED
        if name == want and pinned in (None, version)
    ]
    return hits + [f"{n}@{v}" for n, v in sorted(packages) if n == "expo" or n.startswith("@expo/")]


# --- the runtime stage -----------------------------------------------------------------------


class TestRuntimeStage:
    def test_the_image_is_a_builder_and_a_runtime_stage(self) -> None:
        stages = _stages(_text())
        assert [s.name for s in stages] == ["builder", "runtime"]
        assert stages[0].base == stages[1].base, "one pinned base for both"

    def test_the_runtime_stage_copies_only_the_build_output(self) -> None:
        assert _runtime_violations(_text()) == []

    def test_the_one_runtime_command_removes_the_base_images_package_managers(self) -> None:
        runtime = _stages(_text())[-1]
        keywords = [k for k, _ in runtime.instructions]
        (run,) = [a for k, a in runtime.instructions if k == "RUN"]
        assert shlex.split(run) == PRUNE
        assert keywords.index("RUN") < keywords.index("COPY"), "removed before the app lands"

    @pytest.mark.parametrize(
        "prune",
        [
            "rm -rf " + " ".join(BASE_TOOLING),
            "rm -r " + " ".join(BASE_TOOLING[1:]),
            "rm -r " + " ".join(p for p in BASE_TOOLING if "yarn" not in p),
            "rm -r " + " ".join(BASE_TOOLING) + " && npm ci --omit=dev",
        ],
        ids=["force-hides-a-moved-path", "keeps-npm", "keeps-yarn", "installs-after"],
    )
    def test_near_miss_any_other_prune_is_refused(self, prune: str) -> None:
        text = _text()
        start = text.index("RUN rm -r /usr/local/lib/node_modules")
        end = text.index("\n", text.index("/usr/local/bin/yarnpkg", start))
        variant = text[:start] + f"RUN {prune}" + text[end:]
        assert variant != text
        assert _runtime_violations(variant), prune

    def test_near_miss_copying_the_builder_whole_is_refused(self) -> None:
        # main's runtime stage before INT-599
        text = _text()
        before = text.replace(
            f"COPY --from=builder {STANDALONE} /app", "COPY --from=builder /app /app"
        )
        assert before != text
        assert _runtime_violations(before)

    @pytest.mark.parametrize(
        "line",
        [
            "RUN corepack enable && pnpm install --prod --frozen-lockfile",
            "RUN npm ci --omit=dev",
            "COPY . /app",
            "COPY apps/admin-web /app/apps/admin-web",
            "COPY --from=builder /app/node_modules /app/node_modules",
            f"COPY --from=builder {APP}/node_modules {APP}/node_modules",
            "ADD https://registry.npmjs.org/zod/-/zod-3.25.76.tgz /app/",
        ],
        ids=["pnpm-prod", "npm-ci", "context", "sources", "root-modules", "app-modules", "add"],
    )
    def test_near_miss_any_other_runtime_line_is_refused(self, line: str) -> None:
        text = _text()
        assert text.count("\nUSER ") == 1
        variant = text.replace("\nUSER ", f"\n{line}\nUSER ", 1)
        assert _runtime_violations(variant), line

    def test_the_server_is_the_standalone_entry_point(self) -> None:
        assert _entry_point(_text()) == (APP, ["node", "server.js"])

    def test_near_miss_mains_next_start_is_not_the_entry_point(self) -> None:
        # `next start` runs node_modules/.bin/next, which the standalone trace omits
        text = _text()
        before = text.replace(
            'CMD ["node", "server.js"]',
            'CMD ["node_modules/.bin/next", "start", "--port", "3000"]',
        )
        assert before != text
        assert _entry_point(before) != (APP, ["node", "server.js"])

    def test_the_runtime_stays_non_root_with_its_health_check(self) -> None:
        runtime = _stages(_text())[-1]
        keywords = [k for k, _ in runtime.instructions]
        assert keywords.index("USER") > max(i for i, k in enumerate(keywords) if k == "COPY")
        assert dict(runtime.instructions)["USER"] == "10001:10001"
        assert "/healthz" in dict(runtime.instructions)["HEALTHCHECK"]

    def test_next_emits_the_standalone_output(self) -> None:
        pattern = re.compile(r'^\s*output:\s*"standalone",\s*$', re.M)
        assert pattern.search(NEXT_CONFIG.read_text(encoding="utf-8"))
        # near miss: the config without the line
        assert not pattern.search("const config: NextConfig = {\n  poweredByHeader: false,\n};")

    def test_the_console_has_no_public_directory_to_copy(self) -> None:
        # standalone output omits public/; one added later must reach the runtime stage
        assert not (ADMIN_WEB / "public").exists()

    def test_the_compose_cache_mount_is_inside_the_server_directory(self) -> None:
        console = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]["admin-web"]
        assert console["read_only"] is True
        assert f"{APP}/.next/cache" in console["tmpfs"]


# --- what the builder installs ---------------------------------------------------------------


class TestBuilderClosure:
    def test_the_builder_installs_admin_web_and_the_workspace_root_only(self) -> None:
        run = _builder_run()
        assert "--frozen-lockfile" in run
        filters = _install_filters(run)
        assert filters == BUILDER_FILTERS
        assert _importers_for(_lock(), filters) == {".", "apps/admin-web"}

    def test_nothing_the_builder_installs_is_expo_tooling_zod_or_deepmerge(self) -> None:
        lock = _lock()
        installed = _closure(
            lock, _importers_for(lock, _install_filters(_builder_run())), ALL_KINDS
        )
        assert installed, "the walk reached the lockfile"
        assert _named_in(installed) == []

    def test_near_miss_the_mobile_importer_reaches_all_three(self) -> None:
        reached = _named_in(_closure(_lock(), ["apps/mobile"], ALL_KINDS))
        for want in ("@expo/cli@", "zod@3.25.76", "deepmerge@"):
            assert any(hit.startswith(want) for hit in reached), want

    def test_near_miss_a_filter_that_adds_the_mobile_app_is_caught(self) -> None:
        lock = _lock()
        importers = _importers_for(lock, [*BUILDER_FILTERS, "@intake/mobile"])
        assert "apps/mobile" in importers
        assert _named_in(_closure(lock, importers, ALL_KINDS))


# --- the production closure the trace is held to ---------------------------------------------


class TestProductionClosure:
    def test_the_production_closure_holds_no_dev_dependency(self) -> None:
        lock = _lock()
        production = _closure(lock, ["apps/admin-web"], PRODUCTION_KINDS)
        names = {n for n, _ in production}
        assert {"next", "react", "react-dom"} <= names
        dev = {
            name
            for importer in (".", "apps/admin-web")
            for name in (lock["importers"][importer].get("devDependencies") or {})
        }
        assert dev, "the control: both importers declare devDependencies"
        assert not names & dev
        assert _named_in(production) == []

    def test_near_miss_with_dev_dependencies_main_carried_the_build_tooling(self) -> None:
        # what main's runtime stage held: the builder's whole install
        names = {n for n, _ in _closure(_lock(), [".", "apps/admin-web"], ALL_KINDS)}
        assert {"eslint", "typescript", "vitest", "prettier", "jsdom"} <= names


# --- the trace guard: wiring -----------------------------------------------------------------


class TestGuardWiring:
    def test_the_builder_guards_the_trace_it_just_built(self) -> None:
        run = _builder_run()
        assert " || " not in run and ";" not in run, "a failing guard fails the build"
        commands = [c.strip() for c in run.split("&&")]
        build = commands.index("pnpm --filter @intake/admin-web exec next build")
        (listing,) = [i for i, c in enumerate(commands) if c.startswith(PRODUCTION_LIST)]
        (guard,) = [i for i, c in enumerate(commands) if GUARD_IN_CONTEXT in c]
        assert build < listing < guard
        listed = shlex.split(commands[listing].removeprefix(PRODUCTION_LIST))
        assert listed[0] == ">" and len(listed) == 2
        assert shlex.split(commands[guard]) == ["sh", GUARD_IN_CONTEXT, listed[1], TRACE]

    def test_the_guard_is_sent_in_the_build_context(self) -> None:
        lines = [
            line.strip()
            for line in DOCKERIGNORE.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        ]
        assert lines[0] == "*"
        assert f"!{GUARD_IN_CONTEXT}" in lines

    def test_the_guard_is_strict_posix_sh_and_parses(self) -> None:
        text = GUARD.read_text(encoding="utf-8")
        assert text.startswith("#!/bin/sh\n")
        assert "\nset -eu\n" in text
        result = subprocess.run(["sh", "-n", str(GUARD)], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr


# --- the trace guard: behaviour over fixture trees -------------------------------------------

#: The trace a local `next build` of this console produced on 31 Oct 2026, as
#: store entry -> package name (docs/evidence/INT-599.md).
TRACED = {
    "next@16.4.1_babel-plugin-react-compiler@1.0.0_react-dom@19.2.3_react@19.2.3__react@19.2.3": (
        "next"
    ),
    "react@19.2.3": "react",
    "react-dom@19.2.3_react@19.2.3": "react-dom",
    "styled-jsx@5.1.6_react@19.2.3": "styled-jsx",
    "@swc+helpers@0.5.23": "@swc/helpers",
    "@next+env@16.4.1": "@next/env",
    "client-only@0.0.1": "client-only",
}
#: Production entries the trace does not reach (pnpm lists every platform's binary).
UNTRACED = {
    "@next+swc-linux-x64-gnu@16.4.1": "@next/swc-linux-x64-gnu",
    "caniuse-lite@1.0.30001810": "caniuse-lite",
    "scheduler@0.27.0": "scheduler",
}


def _production_list(path: Path, entries: dict[str, str]) -> Path:
    lines = [APP] + [f"/app/node_modules/.pnpm/{e}/node_modules/{n}" for e, n in entries.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _trace(root: Path, entries: dict[str, str]) -> Path:
    """A standalone tree in pnpm's layout: package files in store entries, links elsewhere."""
    standalone = root / "standalone"
    app = standalone / "apps" / "admin-web"
    app.mkdir(parents=True)
    (app / "server.js").write_text("// server\n", encoding="utf-8")
    store = standalone / "node_modules" / ".pnpm"
    hoist = store / "node_modules"
    for entry, name in entries.items():
        package = store / entry / "node_modules" / name
        package.mkdir(parents=True)
        (package / "package.json").write_text(json.dumps({"name": name}), encoding="utf-8")
        link = hoist / name
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(Path("..", *([".."] * name.count("/")), entry, "node_modules", name))
    if "next" in entries.values():
        (next_entry,) = [e for e, n in entries.items() if n == "next"]
        (app / "node_modules").mkdir()
        (app / "node_modules" / "next").symlink_to(
            Path("../../../node_modules/.pnpm", next_entry, "node_modules/next")
        )
    return standalone


def _guard(listing: Path, standalone: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["sh", str(GUARD), str(listing), str(standalone)],
        capture_output=True,
        text=True,
        check=False,
    )


def _plant(standalone: Path, relative: str) -> None:
    path = standalone / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")


class TestGuardBehaviour:
    def test_the_measured_trace_is_accepted(self, tmp_path: Path) -> None:
        listing = _production_list(tmp_path / "production.txt", {**TRACED, **UNTRACED})
        result = _guard(listing, _trace(tmp_path, TRACED))
        assert result.returncode == 0, result.stderr
        assert "7 store entries" in result.stdout

    @pytest.mark.parametrize(
        "entry",
        [
            "typescript@5.9.3",
            "eslint@9.39.5_jiti@2.6.1",
            "jsdom@30.1.3_@noble+hashes@2.4.0",
            "zod@3.25.76",
            "deepmerge@4.3.1",
            "@expo+cli@57.0.19_expo@57.0.17",
        ],
    )
    def test_a_package_outside_the_production_closure_fails_the_build(
        self, tmp_path: Path, entry: str
    ) -> None:
        listing = _production_list(tmp_path / "production.txt", {**TRACED, **UNTRACED})
        standalone = _trace(tmp_path, TRACED)
        _plant(standalone, f"node_modules/.pnpm/{entry}/node_modules/x/package.json")
        result = _guard(listing, standalone)
        assert result.returncode == 1
        assert entry in result.stderr

    @pytest.mark.parametrize(
        "entry",
        ["react@19.2.4", "react-dom@19.2.3", "next@16.4.1"],
        ids=["other-version", "peer-suffix-dropped", "prefix-only"],
    )
    def test_near_miss_an_entry_must_match_exactly(self, tmp_path: Path, entry: str) -> None:
        listing = _production_list(tmp_path / "production.txt", TRACED)
        standalone = _trace(tmp_path, TRACED)
        _plant(standalone, f"node_modules/.pnpm/{entry}/node_modules/x/package.json")
        result = _guard(listing, standalone)
        assert result.returncode == 1
        assert entry in result.stderr

    @pytest.mark.parametrize(
        "relative",
        [
            "node_modules/eslint/package.json",
            "apps/admin-web/node_modules/jsdom/package.json",
            "node_modules/.pnpm/node_modules/typescript/package.json",
            "node_modules/.pnpm/next@16.4.1_x/node_modules/vitest/node_modules/v/package.json",
        ],
        ids=["hoisted-copy", "app-copy", "hoist-dir-file", "nested-in-unknown-entry"],
    )
    def test_a_package_file_outside_a_known_store_entry_fails(
        self, tmp_path: Path, relative: str
    ) -> None:
        listing = _production_list(tmp_path / "production.txt", TRACED)
        standalone = _trace(tmp_path, TRACED)
        _plant(standalone, relative)
        result = _guard(listing, standalone)
        assert result.returncode == 1, relative

    def test_a_file_directly_in_the_store_fails(self, tmp_path: Path) -> None:
        listing = _production_list(tmp_path / "production.txt", TRACED)
        standalone = _trace(tmp_path, TRACED)
        _plant(standalone, "node_modules/.pnpm/lock.yaml")
        assert _guard(listing, standalone).returncode == 1

    def test_an_empty_production_list_fails_closed(self, tmp_path: Path) -> None:
        listing = _production_list(tmp_path / "production.txt", {})
        result = _guard(listing, _trace(tmp_path, TRACED))
        assert result.returncode == 1
        assert "empty" in result.stderr

    def test_a_trace_without_a_store_fails_closed(self, tmp_path: Path) -> None:
        listing = _production_list(tmp_path / "production.txt", TRACED)
        assert _guard(listing, _trace(tmp_path, {})).returncode == 1

    def test_a_missing_production_list_fails_closed(self, tmp_path: Path) -> None:
        standalone = _trace(tmp_path, TRACED)
        assert _guard(tmp_path / "absent.txt", standalone).returncode == 1

    def test_the_guard_takes_exactly_two_arguments(self, tmp_path: Path) -> None:
        result = subprocess.run(["sh", str(GUARD), str(tmp_path)], capture_output=True, text=True)
        assert result.returncode == 2

    def test_the_guard_prints_entry_names_never_file_contents(self, tmp_path: Path) -> None:
        listing = _production_list(tmp_path / "production.txt", TRACED)
        standalone = _trace(tmp_path, TRACED)
        planted = standalone / "node_modules/.pnpm/zod@3.25.76/node_modules/zod/package.json"
        planted.parent.mkdir(parents=True)
        planted.write_text('{"marker": "do-not-print-me"}', encoding="utf-8")
        result = _guard(listing, standalone)
        assert result.returncode == 1
        assert "do-not-print-me" not in result.stdout + result.stderr
