"""INT-019 — the eslint-security verdict: a debt baseline that may only shrink.

Reads ESLint's JSON report on stdin and compares it against
``eslint_security_baseline.json``.

WHY A BASELINE AND NOT A SEVERITY DOWNGRADE. eslint-plugin-security landed
after ~220 TypeScript files were already written, and it reports 272 findings
on that tree — most of them ``detect-object-injection`` on indexing a typed
record, which is the rule's well-known noise. The two ways to make a gate like
that green are to turn rules off and to record what is already there. Turning
rules off is silent forever; a baseline is a file with a number in it that a
human has to increase on purpose, in a diff, with a reviewer.

So: every recommended rule stays at ``error``, and this gate fails when

  - a (file, rule) pair appears that the baseline does not carry, or
  - an existing pair's count goes up.

A count that goes DOWN passes, and prints the smaller number to write back.
The baseline is regenerated with ``--update``, which is a deliberate act.

The baseline is not an allow-list of safe code. It is a list of places nobody
has looked at yet.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BASELINE = Path(__file__).resolve().parent / "eslint_security_baseline.json"


def counts_from_report(report: list[dict[str, object]]) -> Counter[str]:
    """Count findings per "<repo-relative path>::<ruleId>"."""
    counts: Counter[str] = Counter()
    for entry in report:
        raw = str(entry.get("filePath", ""))
        try:
            path = str(Path(raw).resolve().relative_to(REPO))
        except ValueError:
            path = raw
        messages = entry.get("messages")
        if not isinstance(messages, list):
            continue
        for message in messages:
            if not isinstance(message, dict):
                continue
            rule = message.get("ruleId")
            if rule is None:
                # a parse error has no rule; it is always a failure, never
                # something a baseline can carry
                counts[f"{path}::<parse-error>"] += 1
                continue
            counts[f"{path}::{rule}"] += 1
    return counts


def load_baseline(path: Path) -> Counter[str]:
    if not path.is_file():
        raise SystemExit(
            f"eslint-security: {path.name} is missing — the gate cannot decide and will "
            "not pass. Regenerate it with scripts/ci/eslint_security.sh --update."
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    return Counter({str(k): int(v) for k, v in data["findings"].items()})


def write_baseline(path: Path, counts: Counter[str]) -> None:
    payload = {
        "note": (
            "INT-019 eslint-security debt baseline. Every entry is a place nobody has "
            "looked at yet, not a place that is safe. This map may only shrink: the "
            "gate fails on a new (file, rule) pair or a higher count."
        ),
        "findings": dict(sorted(counts.items())),
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update", action="store_true", help="rewrite the baseline")
    parser.add_argument("--baseline", type=Path, default=BASELINE)
    args = parser.parse_args()

    raw = sys.stdin.read().strip()
    if not raw:
        print("eslint-security: ESLint produced no report — the gate did not run")
        return 1
    counts = counts_from_report(json.loads(raw))

    if args.update:
        write_baseline(args.baseline, counts)
        print(f"eslint-security: baseline rewritten with {sum(counts.values())} finding(s)")
        return 0

    baseline = load_baseline(args.baseline)
    parse_errors = sorted(k for k in counts if k.endswith("::<parse-error>"))
    regressions = [
        f"  {key}: {count} (baseline {baseline.get(key, 0)})"
        for key, count in sorted(counts.items())
        if count > baseline.get(key, 0)
    ]
    improvements = [
        f"  {key}: {baseline[key]} -> {counts.get(key, 0)}"
        for key in sorted(baseline)
        if counts.get(key, 0) < baseline[key]
    ]

    total, base_total = sum(counts.values()), sum(baseline.values())
    print(f"eslint-security: {total} finding(s); baseline {base_total}")
    if parse_errors:
        print("PARSE ERRORS (a file the security rules could not read is not a pass):")
        for key in parse_errors:
            print(f"  {key}")
    if regressions:
        print("NEW OR INCREASED findings (the baseline may only shrink):")
        for line in regressions:
            print(line)
        return 1
    if improvements:
        print("Improved — rerun with --update to write the smaller baseline:")
        for line in improvements:
            print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
