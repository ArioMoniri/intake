"""INT-019 — osv-scanner's verdict: fail on critical/high, report the rest.

osv-scanner has no `--severity` flag: it exits non-zero when it finds anything
at all. The acceptance is narrower — "trivy fs/image/IaC + osv-scanner fail on
critical/high" — so the JSON report is read here and the severity is decided
from the CVSS vector OSV publishes.

The base score is COMPUTED from the vector (CVSS v3.0/v3.1, the specification's
own formula, ~30 lines and no dependency) rather than taken from a vendor's
label. A label is a claim by whoever filed the advisory; the vector is the
data. An advisory that carries only a v4.0 vector, or no vector at all, is
UNSCORED — and UNSCORED FAILS, because an advisory nobody has rated is not an
advisory somebody rated harmless, and letting it through would make "no score"
the cheapest way past this gate.

Nothing here suppresses a finding. Lower-severity vulnerabilities are printed
with their score so they stay visible in the log; they do not fail the build,
which is what "fail on critical/high" means.
"""

from __future__ import annotations

import json
import math
import sys
from typing import Any

# CVSS v3.1 §7.1 metric values. Privileges Required depends on Scope.
_AV = {"N": 0.85, "A": 0.62, "L": 0.55, "P": 0.20}
_AC = {"L": 0.77, "H": 0.44}
_PR_UNCHANGED = {"N": 0.85, "L": 0.62, "H": 0.27}
_PR_CHANGED = {"N": 0.85, "L": 0.68, "H": 0.50}
_UI = {"N": 0.85, "R": 0.62}
_CIA = {"H": 0.56, "L": 0.22, "N": 0.00}


def _roundup(value: float) -> float:
    """CVSS v3.1 Appendix A Roundup: up to the next tenth, exactly."""
    scaled = int(round(value * 100_000))
    if scaled % 10_000 == 0:
        return scaled / 100_000.0
    return (math.floor(scaled / 10_000) + 1) / 10.0


def cvss3_base_score(vector: str) -> float | None:
    """Base score for a CVSS v3.0/v3.1 vector string, or None if unparseable."""
    parts = vector.split("/")
    if not parts or not parts[0].startswith("CVSS:3"):
        return None
    metrics: dict[str, str] = {}
    for part in parts[1:]:
        key, _, value = part.partition(":")
        metrics[key] = value
    try:
        scope_changed = metrics["S"] == "C"
        av = _AV[metrics["AV"]]
        ac = _AC[metrics["AC"]]
        pr = (_PR_CHANGED if scope_changed else _PR_UNCHANGED)[metrics["PR"]]
        ui = _UI[metrics["UI"]]
        conf, integ, avail = (_CIA[metrics[m]] for m in ("C", "I", "A"))
    except KeyError:
        return None

    iss = 1 - ((1 - conf) * (1 - integ) * (1 - avail))
    if scope_changed:
        impact = 7.52 * (iss - 0.029) - 3.25 * (iss - 0.02) ** 15
    else:
        impact = 6.42 * iss
    if impact <= 0:
        return 0.0
    exploitability = 8.22 * av * ac * pr * ui
    if scope_changed:
        return _roundup(min(1.08 * (impact + exploitability), 10.0))
    return _roundup(min(impact + exploitability, 10.0))


def score_of(entries: list[dict[str, Any]]) -> float | None:
    """The highest base score any of an advisory's severity entries yields."""
    best: float | None = None
    for entry in entries:
        raw = entry.get("score")
        if not isinstance(raw, str):
            continue
        value = cvss3_base_score(raw)
        if value is None:
            try:  # some feeds publish the numeric score directly
                value = float(raw)
            except ValueError:
                continue
        best = value if best is None else max(best, value)
    return best


def band(score: float | None) -> str:
    if score is None:
        return "UNSCORED"
    if score >= 9.0:
        return "CRITICAL"
    if score >= 7.0:
        return "HIGH"
    if score >= 4.0:
        return "MEDIUM"
    return "LOW"


BLOCKING = frozenset({"CRITICAL", "HIGH", "UNSCORED"})


def main() -> int:
    raw = sys.stdin.read().strip()
    if not raw:
        print("osv-scanner: no report on stdin — the gate did not run")
        return 1
    report = json.loads(raw)

    blocking: list[str] = []
    informational: list[str] = []
    for result in report.get("results", []):
        source = result.get("source", {}).get("path", "?")
        for package in result.get("packages", []):
            info = package.get("package", {})
            name = f"{info.get('name', '?')}@{info.get('version', '?')}"
            for vuln in package.get("vulnerabilities", []):
                ident = vuln.get("id", "?")
                score = score_of(vuln.get("severity") or [])
                level = band(score)
                shown = "unscored" if score is None else f"{score:.1f}"
                line = f"  {level:<9} {ident:<24} {name}  [{source}]  cvss={shown}"
                (blocking if level in BLOCKING else informational).append(line)

    if informational:
        print("osv-scanner: below the fail threshold (reported, not blocking):")
        for line in sorted(informational):
            print(line)
    if blocking:
        print("FAIL: osv-scanner found critical/high (or unscored) advisories:")
        for line in sorted(blocking):
            print(line)
        return 1
    print("OK: osv-scanner found no critical or high advisory")
    return 0


if __name__ == "__main__":
    sys.exit(main())
