#!/usr/bin/env python3
"""INT-544 — which ci.yml lanes a pull request's diff can affect.

A lane job runs this first, on the bare runner's python3 (stdlib only, before
any setup step), and appends its answer to $GITHUB_OUTPUT:

    python=true
    ts=false
    integration=true

Every later step of the job runs unless its lane is exactly `false`. So an
output that is missing, empty or misspelt runs the lane: only a decision this
script made skips one, and it decides `false` only for a pull request whose
diff it could read in full.

What can affect each lane:

  python       every path. 73 tracked Python files read files under apps/
               (session.tsx source slicing, the i18n catalogues, the admin
               fixtures recorded from the API), and the rest of the suite reads
               docs/, files/ and infra/. No diff can skip check-py safely, so
               none does.
  ts           a pnpm workspace that holds a package.json (apps/*, packages/*,
               services/* per pnpm-workspace.yaml), the root TypeScript and
               pnpm configuration, or CI itself. Nothing under the workspaces
               reads tests/, docs/, files/, infra/ or a Python package
               (docs/evidence/INT-544.md records the search).
  integration  anything outside the TypeScript workspaces and the root
               TypeScript configuration. check-py still runs every Python test
               against those files, so a TypeScript-only diff loses nothing by
               skipping the compose tier.

A path under .github/, scripts/ci/ or infra/ci/, or the Makefile, is CI itself
and runs every lane. So does a push (main, tags), an empty diff, a checkout
that is not a two-parent merge commit, and any git error.

The security gates (security.yml) and the `gates` job are not lanes. Nothing
here can skip them (invariant 14).
"""

from __future__ import annotations

import argparse
import fnmatch
import subprocess
import sys
from collections.abc import Iterable, Mapping, Sequence
from enum import Enum
from typing import Final

LANES: Final = ("python", "ts", "integration")

#: CI itself: a change here runs every lane, including the path filter's own code.
CI_PREFIXES: Final = (".github/", "scripts/ci/", "infra/ci/")
CI_FILES: Final = frozenset({"Makefile"})

#: Root files the TypeScript toolchain (pnpm, tsc, eslint, prettier, vitest) reads.
TS_ROOT_FILES: Final = frozenset(
    {
        "package.json",
        "pnpm-lock.yaml",
        "pnpm-workspace.yaml",
        "tsconfig.base.json",
        "tsconfig.json",
        "eslint.config.mjs",
        ".prettierrc",
        ".prettierignore",
        ".npmrc",
        ".nvmrc",
        ".node-version",
    }
)


class PathClass(Enum):
    CI = "ci"
    TS = "ts"
    OTHER = "other"


def workspace_globs(text: str) -> tuple[str, ...]:
    """The `packages:` globs of pnpm-workspace.yaml.

    The file is a flat list; anything else it holds is refused rather than
    guessed at, because a glob read wrongly would make a workspace look like
    plain files and skip its lane.
    """
    globs: list[str] = []
    in_packages = False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line:
            continue
        if not raw.startswith((" ", "-")):
            in_packages = line == "packages:"
            if not in_packages and not line.endswith(":"):
                raise ValueError(f"pnpm-workspace.yaml: unexpected line {raw!r}")
            continue
        if in_packages:
            item = line.strip()
            if not item.startswith("- "):
                raise ValueError(f"pnpm-workspace.yaml: unexpected packages entry {raw!r}")
            glob = item[2:].strip().strip("\"'")
            if not glob or glob.startswith("!"):
                raise ValueError(f"pnpm-workspace.yaml: unsupported glob {raw!r}")
            globs.append(glob)
    if not globs:
        raise ValueError("pnpm-workspace.yaml lists no packages")
    return tuple(globs)


def ts_workspace_roots(tracked: Iterable[str], globs: Sequence[str]) -> frozenset[str]:
    """The workspace directories that hold a tracked package.json."""
    roots: set[str] = set()
    for path in tracked:
        if not path.endswith("/package.json"):
            continue
        directory = path[: -len("/package.json")]
        if any(fnmatch.fnmatchcase(directory, glob) for glob in globs):
            roots.add(directory)
    return frozenset(roots)


def classify(path: str, ts_roots: frozenset[str]) -> PathClass:
    if path in CI_FILES or path.startswith(CI_PREFIXES):
        return PathClass.CI
    if path in TS_ROOT_FILES:
        return PathClass.TS
    if any(path.startswith(f"{root}/") for root in ts_roots):
        return PathClass.TS
    return PathClass.OTHER


def every_lane() -> dict[str, bool]:
    return dict.fromkeys(LANES, True)


def lanes_for(paths: Sequence[str], ts_roots: frozenset[str]) -> dict[str, bool]:
    if not paths:
        return every_lane()
    classes = {classify(path, ts_roots) for path in paths}
    if PathClass.CI in classes:
        return every_lane()
    return {
        "python": True,
        "ts": PathClass.TS in classes,
        "integration": PathClass.OTHER in classes,
    }


def _git(*args: str) -> str:
    # fixed argv; git is resolved from PATH on the runner, as every job step does
    return subprocess.run(  # noqa: S603  # nosec B603 B607
        ["git", *args],  # noqa: S607
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    ).stdout


def changed_paths(base: str, head: str) -> list[str]:
    # --no-renames: a move out of a workspace must show the workspace path too.
    out = _git("diff", "--name-only", "--no-renames", "-z", base, head)
    return [path for path in out.split("\0") if path]


def decide(event: str, base: str, head: str) -> tuple[dict[str, bool], str]:
    if event != "pull_request":
        return every_lane(), f"a {event or 'non-pull-request'} run runs every lane"
    try:
        parents = _git("rev-list", "--parents", "-n", "1", head).split()
        if len(parents) != 3:
            return every_lane(), "the checkout is not a two-parent merge commit"
        paths = changed_paths(base, head)
        globs = workspace_globs(_git("show", f"{head}:pnpm-workspace.yaml"))
        roots = ts_workspace_roots(_git("ls-files", "-z").split("\0"), globs)
    except (subprocess.SubprocessError, OSError, ValueError) as err:
        return (
            every_lane(),
            f"the diff could not be read ({type(err).__name__}); running every lane",
        )
    lanes = lanes_for(paths, roots)
    skipped = [lane for lane in LANES if not lanes[lane]]
    reason = f"{len(paths)} changed paths; skipped: {', '.join(skipped) or 'none'}"
    return lanes, reason


def render(lanes: Mapping[str, bool]) -> str:
    return "".join(f"{lane}={'true' if lanes[lane] else 'false'}\n" for lane in LANES)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--event", required=True, help="github.event_name")
    parser.add_argument("--base", default="HEAD^1", help="the base side of the merge commit")
    parser.add_argument("--head", default="HEAD", help="the merge commit under test")
    args = parser.parse_args(argv)
    lanes, reason = decide(args.event, args.base, args.head)
    sys.stdout.write(render(lanes))
    sys.stderr.write(f"lanes: {reason}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
