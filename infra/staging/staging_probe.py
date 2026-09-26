"""INT-345 staging probe. smoke.sh runs it inside the api container.

Subcommands:

``env``
    Refuse unless this process has the staging posture: ``INTAKE_ENV`` is
    staging, no dev gate is present, and the KEK mode that the API's own
    settings resolve is Transit.
``write``
    Encrypt one synthetic record through the API's own cipher wiring
    (``intake_api.app.wiring_from_env``) and print the packed envelope on
    stdout. The output holds ciphertext and a Transit-wrapped DEK. No
    plaintext is printed.
``read``
    Decrypt the packed envelope read from stdin and compare it with the
    synthetic plaintext. Exit 0 only on an exact match.

The restart test is: ``write``, restart the api container (then OpenBao,
then unseal), ``read``. With the process-local KEK the read fails, because a
new process holds new keys. With Transit the KEK lives in OpenBao's file
storage and the read passes. That is the acceptance's "a note written before
a restart decrypts after it".

Why this is not done over HTTP: a staging API without dev gates has no
authentication tier that can write a note. The dev bearers are dev gates,
and the OTP tier needs an SMS vendor and device attestation, both
awaiting-human. So the probe drives the same cipher the API wires, in the
same container, with the same OpenBao token, instead of going through a
route.

Every message names states and exception classes, never content
(invariant 6). The record is synthetic by construction.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Mapping, Sequence
from typing import TextIO

from intake_api import settings as api_settings
from intake_platform.envelope import EncryptedField, EnvelopeCipher

__all__ = [
    "PROBE_AAD",
    "PROBE_PLAINTEXT",
    "PROBE_TENANT",
    "dev_prefix",
    "environment_offences",
    "main",
    "read_record",
    "write_record",
]

#: Transit key ``tenant-staging-restart-probe``, created by init.sh. It is
#: not a real tenant, so the probe never touches a tenant's KEK.
PROBE_TENANT = "staging-restart-probe"
PROBE_AAD = b"intake-staging/restart-probe/v1"
PROBE_PLAINTEXT = b"SYNTHETIC staging restart-probe record; no patient data"

STAGING_ENV = "staging"
TRANSIT = "transit"
DECRYPTED = "restart-probe: decrypted"


def dev_prefix() -> str:
    """The dev-gate prefix, derived from the API's own gate names so that a
    renamed gate moves this check with it."""
    return os.path.commonprefix(
        [
            api_settings.ENV_TOKEN_PATIENT,
            api_settings.ENV_TOKEN_ADMIN,
            api_settings.ENV_DEV_OTP_PEEK,
            api_settings.ENV_DEV_ALLOW_UNATTESTED,
        ]
    )


def environment_offences(environ: Mapping[str, str], kek_mode: str) -> list[str]:
    """Every way this process departs from the staging posture. Names only."""
    offences: list[str] = []
    if environ.get("INTAKE_ENV", "") != STAGING_ENV:
        offences.append("INTAKE_ENV is not staging")
    prefix = dev_prefix()
    gates = sorted(name for name in environ if name.startswith(prefix))
    if gates:
        # present at all, even empty: staging carries no dev gate
        offences.append("dev gate(s) present: " + ", ".join(gates))
    if kek_mode != TRANSIT:
        offences.append(f"KEK mode resolves to {kek_mode!r}, not transit")
    return offences


def write_record(cipher: EnvelopeCipher) -> str:
    return cipher.encrypt_field(PROBE_TENANT, PROBE_PLAINTEXT, PROBE_AAD).pack()


def read_record(cipher: EnvelopeCipher, packed: str) -> None:
    """Raise unless ``packed`` opens to the synthetic plaintext."""
    field = EncryptedField.unpack(packed.strip())
    if cipher.decrypt_field(PROBE_TENANT, field, PROBE_AAD) != PROBE_PLAINTEXT:
        raise ValueError("decrypted record does not match the synthetic plaintext")


def _api_kek_mode() -> str:
    return api_settings.ApiSettings.from_env().kek_mode


def _api_cipher() -> EnvelopeCipher:
    # imported here: the refusal path must not build engines or clients
    from intake_api.app import wiring_from_env

    return wiring_from_env().cipher


def main(
    argv: Sequence[str],
    *,
    environ: Mapping[str, str] = os.environ,
    kek_mode: Callable[[], str] = _api_kek_mode,
    cipher_factory: Callable[[], EnvelopeCipher] = _api_cipher,
    stdin: TextIO = sys.stdin,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    if len(argv) != 1 or argv[0] not in {"env", "write", "read"}:
        print("usage: staging_probe.py env|write|read", file=stderr)
        return 64
    offences = environment_offences(environ, kek_mode())
    if offences:
        print("staging posture refused: " + "; ".join(offences), file=stderr)
        return 2
    command = argv[0]
    if command == "env":
        print("staging posture: ok (staging, no dev gate, transit KEK)", file=stdout)
        return 0
    try:
        cipher = cipher_factory()
        if command == "write":
            packed = write_record(cipher)
        else:
            read_record(cipher, stdin.read())
    except Exception as err:  # noqa: BLE001 - report the class only (invariant 6)
        verb = "encrypt" if command == "write" else "decrypt"
        print(f"restart-probe: {verb} failed ({type(err).__name__})", file=stderr)
        return 1
    print(packed if command == "write" else DECRYPTED, file=stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
