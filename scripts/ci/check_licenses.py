"""INT-019 — dependency licence allow-list gate (invariant 14; files/10 §6).

Reads the licence metadata that is offline-derivable after `uv sync` and
`pnpm install`:
  - Python: installed distributions' METADATA (License-Expression, trove
    classifiers, License field) via importlib.metadata,
  - Node: every package.json under node_modules (pnpm virtual-store layout
    and plain layouts), our own workspace packages excluded.

Anything not on the allow-list fails, loudly: AGPL/SSPL are named as denied,
everything else unresolvable is UNKNOWN — both are violations. OR-expressions
pass when any branch is allowed; AND-expressions need every branch allowed.

Honest coverage limits (printed on every run): this gate reads DECLARED
metadata only — it does not audit vendored source, native binaries inside
wheels, or transitive licences a package misdeclares. It is a tripwire for
the licence classes we must never ship (AGPL/SSPL/unknown), not legal review.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterator
from importlib import metadata
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# The explicit allow-list. Extensions beyond the INT-019 baseline carry their
# justification inline and were each verified against the raw licence text of
# the package that introduced them (CLAUDE.md invariant 19 discipline).
ALLOWED = {
    "MIT",
    "Apache-2.0",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "ISC",
    "PSF-2.0",
    "Python-2.0",  # PSF family (older packages declare Python-2.0)
    "MPL-2.0",
    "OFL-1.1",
    "Unlicense",
    "Zlib",
    "0BSD",  # BSD-0-clause (tslib et al.): strictly more permissive than BSD-2
    "MIT-0",  # MIT no-attribution: strictly more permissive than MIT
    "BlueOak-1.0.0",  # permissive; jackspeak/path-scurry in the pnpm tree
    "CC0-1.0",  # public-domain dedication (spdx data packages)
    "CC-BY-4.0",  # attribution-only; data packages (caniuse-lite) and corpora
    "CC-BY-3.0",  # attribution-only; spdx-exceptions data package
    "Apache-2.0 WITH LLVM-exception",
    "HPND",  # Pillow's historical permissive licence
    "Public-Domain",
    "BSL-1.0",  # Boost Software License 1.0 (permissive) — NOT BUSL-1.1; torch bundles Boost
    "CNRI-Python",  # OSI-approved historical Python licence; the `regex` package
}

DENIED_PREFIXES = ("AGPL", "SSPL")

# Our own workspace packages are not third-party dependencies.
FIRST_PARTY_PYTHON = {"intake", "intake-platform", "intake-probes"}

# Documented per-package exceptions — exact names, never prefixes, each with the
# reason it is tolerated. Anything new with the same licence still fails, which
# forces a conscious decision instead of silent growth.
EXCEPTIONS = {
    "@expo/ngrok-bin": (
        "dev-only Expo tunnel helper wrapping the proprietary ngrok agent; "
        "devDependency tree only, never part of a shipped artifact"
    ),
    "psycopg": (
        "LGPL-3.0 PostgreSQL driver used unmodified as a dynamically-imported "
        "library; source-offer met upstream; re-review if vendored or modified"
    ),
    "psycopg-binary": "see psycopg — same upstream, binary wheel variant",
}
# @expo/ngrok-bin fans out into per-platform binary packages with no licence
# metadata of their own (…-darwin-arm64, …-linux-x64, …); they inherit the
# parent's exception and nothing else does.
EXCEPTION_PREFIXES = {"@expo/ngrok-bin-": "platform binary of @expo/ngrok-bin (see above)"}

# Raw licence strings seen in the wild -> SPDX id.
ALIASES = {
    "MIT": "MIT",
    "MIT LICENSE": "MIT",
    "MIT STYLE": "MIT",  # lupa's declaration; its LICENSE blob is the MIT text
    "EXPAT": "MIT",
    "APACHE": "Apache-2.0",
    "APACHE 2.0": "Apache-2.0",
    "APACHE-2.0": "Apache-2.0",
    "APACHE 2": "Apache-2.0",
    "APACHE LICENSE 2.0": "Apache-2.0",
    "APACHE LICENSE, VERSION 2.0": "Apache-2.0",
    "APACHE 2.0 LICENSE": "Apache-2.0",  # transformers' declaration
    "APACHE SOFTWARE LICENSE": "Apache-2.0",
    "APACHE LICENSE VERSION 2.0": "Apache-2.0",
    "BSD": "BSD-3-Clause",
    "BSD LICENSE": "BSD-3-Clause",
    "BSD-3-CLAUSE": "BSD-3-Clause",
    "BSD 3-CLAUSE": "BSD-3-Clause",
    "3-CLAUSE BSD LICENSE": "BSD-3-Clause",
    "NEW BSD LICENSE": "BSD-3-Clause",
    "BSD-2-CLAUSE": "BSD-2-Clause",
    "BSD 2-CLAUSE": "BSD-2-Clause",
    "0BSD": "0BSD",
    "BSD ZERO CLAUSE LICENSE": "0BSD",
    "ISC": "ISC",
    "ISC LICENSE (ISCL)": "ISC",
    "MPL-2.0": "MPL-2.0",
    "MPL 2.0": "MPL-2.0",
    "MOZILLA PUBLIC LICENSE 2.0 (MPL 2.0)": "MPL-2.0",
    "PSF": "PSF-2.0",
    "PSF-2.0": "PSF-2.0",
    "PSF LICENSE": "PSF-2.0",
    "PYTHON SOFTWARE FOUNDATION LICENSE": "PSF-2.0",
    "PYTHON-2.0": "Python-2.0",
    "PYTHON-2.0.1": "Python-2.0",
    "OFL-1.1": "OFL-1.1",
    "SIL OPEN FONT LICENSE 1.1": "OFL-1.1",
    "UNLICENSE": "Unlicense",
    "THE UNLICENSE": "Unlicense",
    "THE UNLICENSE (UNLICENSE)": "Unlicense",
    "ZLIB": "Zlib",
    "ZLIB/LIBPNG LICENSE": "Zlib",
    "MIT-0": "MIT-0",
    "BLUEOAK-1.0.0": "BlueOak-1.0.0",
    "BLUE OAK MODEL LICENSE": "BlueOak-1.0.0",
    "CC0-1.0": "CC0-1.0",
    "CC-BY-4.0": "CC-BY-4.0",
    "CC-BY-3.0": "CC-BY-3.0",
    "HPND": "HPND",
    "HISTORICAL PERMISSION NOTICE AND DISCLAIMER (HPND)": "HPND",
    "PUBLIC DOMAIN": "Public-Domain",
    "AGPL-3.0": "AGPL-3.0-only",
    "AGPL-3.0-ONLY": "AGPL-3.0-only",
    "AGPL-3.0-OR-LATER": "AGPL-3.0-or-later",
    "GNU AFFERO GENERAL PUBLIC LICENSE V3": "AGPL-3.0-only",
    "SSPL-1.0": "SSPL-1.0",
}

CLASSIFIER_MAP = {
    "License :: OSI Approved :: MIT License": "MIT",
    "License :: OSI Approved :: Apache Software License": "Apache-2.0",
    "License :: OSI Approved :: BSD License": "BSD-3-Clause",
    "License :: OSI Approved :: ISC License (ISCL)": "ISC",
    "License :: OSI Approved :: Python Software Foundation License": "PSF-2.0",
    "License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)": "MPL-2.0",
    "License :: OSI Approved :: The Unlicense (Unlicense)": "Unlicense",
    "License :: OSI Approved :: zlib/libpng License": "Zlib",
    "License :: OSI Approved :: Historical Permission Notice and Disclaimer (HPND)": "HPND",
    "License :: Public Domain": "Public-Domain",
    "License :: OSI Approved :: GNU Affero General Public License v3": "AGPL-3.0-only",
    "License :: OSI Approved :: GNU Affero General Public License v3 or later (AGPLv3+)": (
        "AGPL-3.0-or-later"
    ),
}


def _split_top_level(expr: str, op: str) -> list[str]:
    """Split an SPDX expression on OR/AND at parenthesis depth 0."""
    parts: list[str] = []
    depth = 0
    token = f" {op} "
    buf = ""
    i = 0
    upper = expr.upper()
    while i < len(expr):
        ch = expr[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if depth == 0 and upper.startswith(token, i):
            parts.append(buf)
            buf = ""
            i += len(token)
            continue
        buf += ch
        i += 1
    parts.append(buf)
    return [p.strip() for p in parts if p.strip()]


def _normalize_atom(atom: str) -> str:
    atom = atom.strip().strip("()").strip()
    upper = atom.upper()
    if upper in ALIASES:
        return ALIASES[upper]
    return atom


def expression_allowed(expr: str) -> bool:
    expr = expr.strip()
    if expr.startswith("(") and expr.endswith(")") and _balanced(expr[1:-1]):
        expr = expr[1:-1].strip()
    ors = _split_top_level(expr, "OR")
    if len(ors) > 1:
        return any(expression_allowed(part) for part in ors)
    ands = _split_top_level(expr, "AND")
    if len(ands) > 1:
        return all(expression_allowed(part) for part in ands)
    atom = _normalize_atom(expr)
    if atom in ALLOWED:
        return True
    # "X WITH exception" is governed by X for allow-list purposes
    if " WITH " in atom.upper():
        return expression_allowed(atom[: atom.upper().index(" WITH ")])
    return False


def _balanced(s: str) -> bool:
    depth = 0
    for ch in s:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if depth < 0:
            return False
    return depth == 0


def verdict(raw: str) -> str:
    """ALLOWED, DENIED (AGPL/SSPL named), or UNKNOWN."""
    if expression_allowed(raw):
        return "ALLOWED"
    atoms = raw.replace("(", " ").replace(")", " ").upper()
    if any(prefix in atoms for prefix in DENIED_PREFIXES):
        return "DENIED"
    return "UNKNOWN"


def iter_node(node_modules: Path) -> Iterator[tuple[str, str, str]]:
    """Yield (name, version, raw licence) for every third-party node package."""
    if not node_modules.is_dir():
        raise FileNotFoundError(
            f"{node_modules} missing — run `pnpm install` first (invariant 14: never skip)"
        )
    roots = [node_modules]
    pnpm_store = node_modules / ".pnpm"
    if pnpm_store.is_dir():
        roots.extend(sorted(p / "node_modules" for p in pnpm_store.iterdir() if p.is_dir()))
    seen: set[tuple[str, str]] = set()
    for root in roots:
        if not root.is_dir():
            continue
        candidates = list(root.glob("*/package.json")) + list(root.glob("@*/*/package.json"))
        for pkg_json in candidates:
            try:
                data = json.loads(pkg_json.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            name = data.get("name") or pkg_json.parent.name
            version = str(data.get("version", "?"))
            if (name, version) in seen:
                continue
            seen.add((name, version))
            if data.get("private") is True:
                continue  # our own workspace packages are not distributed deps
            resolved = pkg_json.resolve()
            if REPO in resolved.parents and "node_modules" not in resolved.parts:
                continue  # symlink back into the workspace itself
            raw = data.get("license") or data.get("licence")
            if isinstance(raw, dict):
                raw = raw.get("type")
            if raw is None and isinstance(data.get("licenses"), list):
                types = [
                    entry.get("type", "") for entry in data["licenses"] if isinstance(entry, dict)
                ]
                raw = " OR ".join(t for t in types if t)
            yield name, version, str(raw) if raw else ""


def iter_python(python_path: Path | None) -> Iterator[tuple[str, str, str]]:
    """Yield (name, version, raw licence) for installed Python distributions."""
    if python_path is not None:
        dists = metadata.distributions(path=[str(python_path)])
    else:
        dists = metadata.distributions()
    seen: set[tuple[str, str]] = set()
    for dist in dists:
        md = dist.metadata
        name = md["Name"] or "?"
        version = dist.version or "?"
        if (name, version) in seen:
            continue
        seen.add((name, version))
        expr = md.get("License-Expression")
        if expr:
            yield name, version, str(expr)
            continue
        for classifier in md.get_all("Classifier") or []:
            if classifier in CLASSIFIER_MAP:
                yield name, version, CLASSIFIER_MAP[classifier]
                break
        else:
            lic = (md.get("License") or "").strip()
            # a full licence text pasted into the field is not a declaration
            yield name, version, lic if len(lic) <= 120 else lic.splitlines()[0][:120]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node-modules", type=Path, default=REPO / "node_modules")
    parser.add_argument(
        "--python-path",
        type=Path,
        default=None,
        help="scan dist-info under this directory instead of the running environment",
    )
    args = parser.parse_args(argv)

    violations: list[str] = []
    excepted: list[str] = []
    counts = {"node": 0, "python": 0}

    for source, packages in (
        ("node", iter_node(args.node_modules)),
        ("python", iter_python(args.python_path)),
    ):
        for name, version, raw in packages:
            if source == "python" and name in FIRST_PARTY_PYTHON:
                continue
            counts[source] += 1
            v = verdict(raw) if raw else "UNKNOWN"
            if v == "ALLOWED":
                continue
            reason = EXCEPTIONS.get(name) or next(
                (r for p, r in EXCEPTION_PREFIXES.items() if name.startswith(p)), None
            )
            if reason is not None:
                excepted.append(f"  {name}@{version} — {reason}")
                continue
            shown = raw if raw else "(no licence metadata)"
            violations.append(f"  {name}@{version} — {v}: {shown}  [{source}]")

    print(
        f"licence gate: scanned {counts['node']} node packages, "
        f"{counts['python']} python distributions (declared metadata only — "
        "no source audit; AGPL/SSPL/unknown fail)"
    )
    if excepted:
        print(f"EXCEPTIONS (documented in this script, n={len(excepted)}):")
        for line in sorted(excepted):
            print(line)
    if counts["node"] + counts["python"] == 0:
        print("FAIL: nothing scanned — run `pnpm install` and `uv sync` first")
        return 1
    if violations:
        print("VIOLATIONS (licence allow-list, files/10 §6 — AGPL flagged by design):")
        for line in sorted(violations):
            print(line)
        return 1
    print("OK: every dependency licence is on the allow-list")
    return 0


if __name__ == "__main__":
    sys.exit(main())
