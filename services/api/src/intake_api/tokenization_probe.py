"""INT-584 (owner decision D38) — the pseudonym-equality probe.

D38 moves the phone-tokenization key from the synthetic host's env file into
OpenBao with the same key material, so that no pseudonym changes. This probe is
how the host shows that without showing anything else: it derives the
pseudonym of one fixed synthetic number, :data:`PROBE_NUMBER`, with the API's
own Tokenizer construction (:func:`intake_api.state._tokenizer_from_settings`),
and compares it — it never prints it.

``infra/staging/tokenization_key.sh`` runs it in a one-off api container of the
deployed release, with the API's own environment:

    docker compose -p intake-staging run --rm --no-deps -T api \\
        python -m intake_api.tokenization_probe record|compare

- ``record``: before anything moves, the env copy of the key arrives on
  stdin. stdout is a one-way fingerprint of the probe number's pseudonym under
  it (SHA-256, domain-separated), which the host keeps in a root-only file. It
  is neither the key nor the pseudonym, and nothing but that file sees it.
- ``compare``: the before-fingerprint arrives on stdin. The key is resolved
  exactly as the API resolves it at boot
  (:func:`intake_api.tokenization_key.with_tokenization_key`: OpenBao, with the
  API's own token). stdout is ``equal`` or ``differ`` and nothing else, ever;
  the exit code is 0 for equal, 1 for differ, and 2 when there is nothing to
  compare (no before-record, no key), which also prints ``differ``.

No mode prints the key, the pseudonym or the number. A refusal on stderr names
a state, never a value (invariant 6).
"""

from __future__ import annotations

import hashlib
import hmac
import re
import sys
from collections.abc import Callable, Sequence
from dataclasses import replace
from typing import Final, TextIO

from intake_api.settings import ApiSettings
from intake_api.state import _tokenizer_from_settings
from intake_api.tokenization_key import KEY_SHAPE, KvSecrets, with_tokenization_key

__all__ = [
    "CANNOT_COMPARE",
    "DIFFER",
    "EQUAL",
    "FINGERPRINT_SHAPE",
    "PROBE_NUMBER",
    "fingerprint",
    "main",
]

#: Exit codes. EQUAL is also ``record``'s success.
EQUAL, DIFFER, CANNOT_COMPARE = 0, 1, 2
#: Synthetic and fixed: ``+90`` and no mobile prefix, so no subscriber has it.
#: It is an HMAC input and never leaves the process.
PROBE_NUMBER: Final = "+900000000000"
FINGERPRINT_SHAPE: Final = re.compile(r"[0-9a-f]{64}")
_DOMAIN: Final = b"intake.int584.pseudonym-probe.v1\x00"
_USAGE: Final = "usage: python -m intake_api.tokenization_probe record|compare"


def fingerprint(settings: ApiSettings) -> str | None:
    """The probe number's pseudonym under ``settings``' key, hashed one way;
    ``None`` without a key. The Tokenizer is built as the API builds it."""
    tokenizer = _tokenizer_from_settings(settings)
    if tokenizer is None:
        return None
    pseudonym = tokenizer.pseudonym(PROBE_NUMBER)
    return hashlib.sha256(_DOMAIN + pseudonym.encode("utf-8")).hexdigest()


def _record(stdin: TextIO, stdout: TextIO, stderr: TextIO, settings: ApiSettings) -> int:
    key = stdin.read().strip()
    if not KEY_SHAPE.fullmatch(key):
        print("record: stdin holds no well-formed tokenization key", file=stderr)
        return CANNOT_COMPARE
    value = fingerprint(replace(settings, tokenization_key=key))
    if value is None:
        print("record: no tokenizer could be built", file=stderr)
        return CANNOT_COMPARE
    print(value, file=stdout)
    return EQUAL


def _compare(
    stdin: TextIO,
    stdout: TextIO,
    stderr: TextIO,
    settings: ApiSettings,
    secrets_reader: KvSecrets | None,
) -> int:
    before = stdin.read().strip()
    if not FINGERPRINT_SHAPE.fullmatch(before):
        print("differ", file=stdout)
        print("compare: no before-record on stdin to compare against", file=stderr)
        return CANNOT_COMPARE
    resolved = with_tokenization_key(settings, secrets_reader)
    after = fingerprint(resolved)
    if after is None:
        print("differ", file=stdout)
        print(f"compare: the API reads no key ({resolved.tokenization_key_refusal})", file=stderr)
        return CANNOT_COMPARE
    if hmac.compare_digest(before, after):
        print("equal", file=stdout)
        return EQUAL
    print("differ", file=stdout)
    return DIFFER


def main(
    argv: Sequence[str],
    *,
    stdin: TextIO,
    stdout: TextIO,
    stderr: TextIO,
    settings_factory: Callable[[], ApiSettings] = ApiSettings.from_env,
    secrets_reader: KvSecrets | None = None,
) -> int:
    if len(argv) != 1 or argv[0] not in ("record", "compare"):
        print(_USAGE, file=stderr)
        return CANNOT_COMPARE
    settings = settings_factory()
    if argv[0] == "record":
        return _record(stdin, stdout, stderr, settings)
    return _compare(stdin, stdout, stderr, settings, secrets_reader)


if __name__ == "__main__":  # pragma: no cover — the container entry point
    sys.exit(main(sys.argv[1:], stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr))
