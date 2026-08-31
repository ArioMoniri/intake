"""INT-019 — TCKN checksum validator behind scripts/ci/phi_scan.sh.

Reads grep output lines ("path:line:content") on stdin, extracts every 11-digit
candidate bounded by non-digits, and echoes only the lines that carry a
checksum-VALID TCKN. An 11-digit run that fails the checksum is noise (order
ids, timestamps), not an identity number — flagging it would train people to
ignore the gate.

Checksum (resmi algoritma): d1 != 0;
  d10 = ((d1+d3+d5+d7+d9)*7 - (d2+d4+d6+d8)) mod 10;
  d11 = (d1+...+d10) mod 10.
"""

from __future__ import annotations

import re
import sys

CANDIDATE = re.compile(r"(?<![0-9])[1-9][0-9]{10}(?![0-9])")


def is_valid_tckn(digits: str) -> bool:
    d = [int(c) for c in digits]
    if len(d) != 11 or d[0] == 0:
        return False
    d10 = ((d[0] + d[2] + d[4] + d[6] + d[8]) * 7 - (d[1] + d[3] + d[5] + d[7])) % 10
    if d[9] != d10:
        return False
    return d[10] == sum(d[:10]) % 10


def main() -> int:
    """Filter, never a verdict: it always exits 0.

    The caller decides what a hit means. An exit code here would also be read
    by `set -o pipefail` in phi_scan.sh, which would turn "found something"
    into "the pipeline broke" and lose the very lines it just selected.
    """
    for line in sys.stdin:
        line = line.rstrip("\n")
        for candidate in CANDIDATE.findall(line):
            if is_valid_tckn(candidate):
                sys.stdout.write(line + "\n")
                break
    return 0


if __name__ == "__main__":
    sys.exit(main())
