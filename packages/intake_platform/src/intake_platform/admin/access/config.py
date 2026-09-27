"""Building :class:`~intake_platform.admin.access.IdentityWiring` from a deployment (INT-366).

The console process and the scheduled job read the same four facts, so they
are read in one place:

- ``INTAKE_ADMIN_KEYCLOAK_URL`` and ``INTAKE_ADMIN_KEYCLOAK_REALM`` — where the
  Keycloak admin API is, and which realm holds the staff accounts;
- the confidential client's id and secret — read from OpenBao KV at
  ``admin/keycloak-access`` (keys ``client_id``, ``client_secret``), never from
  the environment (invariant 14);
- ``INTAKE_ADMIN_OPENBAO_ALIAS_MOUNT_ACCESSOR`` — the accessor of the OpenBao
  auth mount whose aliases are Keycloak user ids;
- the console systems file, ``infra/admin/console-accounts.yaml`` (overridable
  with ``INTAKE_ADMIN_CONSOLE_ACCOUNTS_PATH``).

Any of them absent raises :class:`IdentityUnconfigured`, and the caller keeps
the review and offboarding unconfigured (503) or refuses the job run. There
is no default for any of them: a guessed realm or mount would look configured
while pointing at the wrong accounts.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Final

import httpx

from intake_platform.admin.access import IdentityWiring
from intake_platform.admin.access.keycloak import KeycloakAdminDirectory
from intake_platform.admin.access.openbao import OpenBaoLeaseRevoker
from intake_platform.admin.access.systems import load_console_systems

if TYPE_CHECKING:
    from intake_platform.secrets import SecretsProvider

__all__ = [
    "CONSOLE_ACCOUNTS_PATH",
    "ENV_ACCOUNTS_PATH",
    "ENV_KEYCLOAK_REALM",
    "ENV_KEYCLOAK_URL",
    "ENV_OPENBAO_MOUNT",
    "KEYCLOAK_CLIENT_KV_PATH",
    "IdentityUnconfigured",
    "identity_from_env",
]

ENV_KEYCLOAK_URL: Final = "INTAKE_ADMIN_KEYCLOAK_URL"
ENV_KEYCLOAK_REALM: Final = "INTAKE_ADMIN_KEYCLOAK_REALM"
ENV_OPENBAO_MOUNT: Final = "INTAKE_ADMIN_OPENBAO_ALIAS_MOUNT_ACCESSOR"
ENV_ACCOUNTS_PATH: Final = "INTAKE_ADMIN_CONSOLE_ACCOUNTS_PATH"
KEYCLOAK_CLIENT_KV_PATH: Final = "admin/keycloak-access"

#: The committed list, resolved from this file so the job finds it whatever
#: directory the scheduler starts it in.
CONSOLE_ACCOUNTS_PATH: Final = (
    Path(__file__).resolve().parents[6] / "infra" / "admin" / "console-accounts.yaml"
)

_TIMEOUT_S: Final = 10.0


class IdentityUnconfigured(Exception):
    """A deployment fact the identity wiring needs is absent."""


def _required(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise IdentityUnconfigured(f"{name} is not set")
    return value


def identity_from_env(env: Mapping[str, str], secrets: SecretsProvider) -> IdentityWiring:
    base_url = _required(env, ENV_KEYCLOAK_URL)
    if not base_url.startswith("https://"):
        raise IdentityUnconfigured(f"{ENV_KEYCLOAK_URL} must be an https origin")
    realm = _required(env, ENV_KEYCLOAK_REALM)
    mount = _required(env, ENV_OPENBAO_MOUNT)
    try:
        credentials = secrets.get_kv(KEYCLOAK_CLIENT_KV_PATH)
    except (httpx.HTTPError, KeyError, ValueError):
        raise IdentityUnconfigured(
            f"the Keycloak admin client is not in OpenBao at {KEYCLOAK_CLIENT_KV_PATH}"
        ) from None
    client_id, client_secret = credentials.get("client_id"), credentials.get("client_secret")
    if not isinstance(client_id, str) or not isinstance(client_secret, str):
        raise IdentityUnconfigured(f"{KEYCLOAK_CLIENT_KV_PATH} lacks client_id or client_secret")
    accounts = Path(env.get(ENV_ACCOUNTS_PATH) or CONSOLE_ACCOUNTS_PATH)
    return IdentityWiring(
        directory=KeycloakAdminDirectory(
            httpx.Client(base_url=base_url, timeout=_TIMEOUT_S),
            realm=realm,
            client_id=client_id,
            client_secret=client_secret,
        ),
        # the process's own OpenBao client: its token must carry the
        # offboarding policy in docs/runbooks/access-review.md
        leases=OpenBaoLeaseRevoker(secrets._client, alias_mount_accessor=mount),
        systems=load_console_systems(accounts),
    )
