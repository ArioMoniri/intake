"""The console accounts that live outside Keycloak and OpenBao (INT-366; files/08 §2.4).

files/08 §2.4 names them — "the Grafana / Langfuse / Unleash accounts" — and
calls them "three separate identity stores". Offboarding must reach every one
of them in the same action. ``infra/admin/console-accounts.yaml`` is where
they are enumerated; this module loads it strictly.

Each entry says how its revocation happens:

- ``programmatic`` — an adapter registered in code revokes it. The loader
  refuses an entry that names no registered adapter, so a configured system
  can never be *assumed* revoked by code that does not exist.
- ``manual`` — a person does it, following the runbook section the entry
  links. Offboarding lists it, the offboarding stays incomplete, and only an
  audited confirmation closes it.

Nothing is optional and nothing is skipped: an unknown key, a missing runbook
link or an empty list refuses the whole file rather than loading part of it.
"""

from __future__ import annotations

import enum
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol

import yaml

__all__ = [
    "BUILT_IN_SYSTEMS",
    "AccountRevoker",
    "ConsoleAccountSystem",
    "ConsoleSystemsRefused",
    "Revocation",
    "load_console_systems",
]

#: The steps every offboarding runs through the two built-in adapters. An
#: entry in the file may not reuse one of these ids.
BUILT_IN_SYSTEMS: Final = ("keycloak_account", "keycloak_sessions", "openbao_leases")

_SYSTEM_ID: Final = re.compile(r"[a-z][a-z0-9_]{1,31}")
_RUNBOOK: Final = re.compile(r"docs/runbooks/[a-z0-9_-]+\.md#[a-z0-9-]+")
_KEYS: Final = frozenset({"id", "revocation", "runbook"})


class ConsoleSystemsRefused(Exception):
    """The configuration would leave a system unrevoked or unlisted."""


class Revocation(enum.StrEnum):
    PROGRAMMATIC = "programmatic"
    MANUAL = "manual"


class AccountRevoker(Protocol):
    """A programmatic adapter for one console system."""

    def revoke_for(self, subject: str) -> int: ...


@dataclass(frozen=True)
class ConsoleAccountSystem:
    id: str
    revocation: Revocation
    #: ``docs/runbooks/<file>.md#<anchor>`` — what a person does for a manual
    #: step, and what an operator checks for a programmatic one.
    runbook: str


def _entry(raw: object, adapters: Mapping[str, AccountRevoker]) -> ConsoleAccountSystem:
    if not isinstance(raw, Mapping) or set(raw) != _KEYS:
        raise ConsoleSystemsRefused(f"each system takes exactly {sorted(_KEYS)}")
    system_id, revocation, runbook = raw["id"], raw["revocation"], raw["runbook"]
    if not isinstance(system_id, str) or not _SYSTEM_ID.fullmatch(system_id):
        raise ConsoleSystemsRefused("a system id is not a lower-case identifier")
    if system_id in BUILT_IN_SYSTEMS:
        raise ConsoleSystemsRefused(f"{system_id} is a built-in step, not a configured system")
    if not isinstance(runbook, str) or not _RUNBOOK.fullmatch(runbook):
        raise ConsoleSystemsRefused(f"{system_id} links no runbook section")
    try:
        kind = Revocation(revocation)
    except ValueError:
        raise ConsoleSystemsRefused(f"{system_id} has an unknown revocation kind") from None
    if kind is Revocation.PROGRAMMATIC and system_id not in adapters:
        raise ConsoleSystemsRefused(
            f"{system_id} claims programmatic revocation but no adapter is registered for it"
        )
    return ConsoleAccountSystem(id=system_id, revocation=kind, runbook=runbook)


def load_console_systems(
    path: Path, adapters: Mapping[str, AccountRevoker] | None = None
) -> tuple[ConsoleAccountSystem, ...]:
    registered: Mapping[str, AccountRevoker] = adapters if adapters is not None else {}
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as err:
        raise ConsoleSystemsRefused(
            f"the console-accounts file is unreadable ({type(err).__name__})"
        ) from None
    if not isinstance(payload, Mapping) or set(payload) != {"schema_version", "systems"}:
        raise ConsoleSystemsRefused("the file takes exactly schema_version and systems")
    if payload["schema_version"] != 1:
        raise ConsoleSystemsRefused("unknown schema_version")
    systems = payload["systems"]
    if not isinstance(systems, list) or not systems:
        raise ConsoleSystemsRefused("an empty system list would skip every console account")
    loaded = tuple(_entry(raw, registered) for raw in systems)
    ids = [system.id for system in loaded]
    if len(set(ids)) != len(ids):
        raise ConsoleSystemsRefused("a system is listed twice")
    return loaded
