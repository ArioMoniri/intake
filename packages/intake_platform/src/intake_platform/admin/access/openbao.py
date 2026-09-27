"""OpenBao behind :class:`~.directory.LeaseRevoker` (INT-366; files/08 §2.4).

files/08 §2.4: offboarding revokes "OIDC sessions **and** OpenBao leases". An
OpenBao lease belongs to the token that created it, and revoking a token
revokes every lease it created, so revoking a person's leases means revoking
the tokens their identity holds. The calls, all documented OpenBao API:

1. ``POST /v1/identity/lookup/entity`` with the alias name (the Keycloak user
   id, which is the ``sub`` OpenBao's JWT/OIDC auth mount records) and that
   mount's accessor — the person's entity, or 204 when they have none;
2. ``POST /v1/identity/entity/id/<id>`` with ``{"disabled": true}`` — every
   token tied to the entity stops working at once, including one created
   between the listing below and its revocation;
3. ``GET /v1/auth/token/accessors?list=true``, then
   ``POST /v1/auth/token/lookup-accessor`` for each — which tokens carry that
   entity id;
4. ``POST /v1/auth/token/revoke-accessor`` for each of those — the token and
   its leases are gone.

The token this adapter runs with needs exactly those capabilities; the policy
is written out in docs/runbooks/access-review.md. A token that has expired
between steps 3 and 4 answers "invalid accessor" and has no leases left to
revoke. Any other refusal raises :class:`~.directory.RevocationFailed`: the
step is reported failed, never assumed done.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Final

import httpx

from intake_platform.admin.access.directory import RevocationFailed, is_subject

__all__ = ["OpenBaoLeaseRevoker"]

_ACCESSOR_SHAPE: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


def _data(response: httpx.Response) -> object:
    """The ``data`` member of an OpenBao answer; a body that is not a JSON
    object is a refusal, not an empty answer."""
    try:
        body = response.json()
    except ValueError:
        raise RevocationFailed("OpenBao answered with a body that is not JSON") from None
    return body.get("data") if isinstance(body, Mapping) else None


class OpenBaoLeaseRevoker:
    """:class:`~.directory.LeaseRevoker` over the OpenBao identity and token APIs."""

    def __init__(self, client: httpx.Client, *, alias_mount_accessor: str) -> None:
        if not _ACCESSOR_SHAPE.fullmatch(alias_mount_accessor):
            raise ValueError("the auth mount accessor is not id-shaped")
        self._client = client
        self._mount = alias_mount_accessor

    def _post(self, path: str, body: Mapping[str, Any]) -> httpx.Response:
        try:
            return self._client.post(path, json=dict(body))
        except httpx.HTTPError as err:
            raise RevocationFailed(f"OpenBao could not be reached ({type(err).__name__})") from None

    def _entity(self, subject: str) -> str | None:
        response = self._post(
            "/v1/identity/lookup/entity",
            {"alias_name": subject, "alias_mount_accessor": self._mount},
        )
        if response.status_code == 204:
            return None
        if response.status_code != 200:
            raise RevocationFailed(f"entity lookup answered {response.status_code}")
        data = _data(response)
        entity = data.get("id") if isinstance(data, Mapping) else None
        if not isinstance(entity, str) or not _ACCESSOR_SHAPE.fullmatch(entity):
            raise RevocationFailed("entity lookup answered without a usable id")
        return entity

    def _accessors(self) -> list[str]:
        try:
            response = self._client.get("/v1/auth/token/accessors", params={"list": "true"})
        except httpx.HTTPError as err:
            raise RevocationFailed(f"OpenBao could not be reached ({type(err).__name__})") from None
        if response.status_code == 404:
            return []
        if response.status_code != 200:
            raise RevocationFailed(f"the accessor list answered {response.status_code}")
        data = _data(response)
        keys = data.get("keys") if isinstance(data, Mapping) else None
        if not isinstance(keys, list) or not all(isinstance(key, str) for key in keys):
            raise RevocationFailed("the accessor list is malformed")
        return list(keys)

    def _holder(self, accessor: str) -> str | None:
        response = self._post("/v1/auth/token/lookup-accessor", {"accessor": accessor})
        if response.status_code == 400:
            # the token expired or was revoked since the listing: nothing left
            return None
        if response.status_code != 200:
            raise RevocationFailed(f"accessor lookup answered {response.status_code}")
        data = _data(response)
        entity = data.get("entity_id") if isinstance(data, Mapping) else None
        return entity if isinstance(entity, str) else None

    def revoke_for(self, subject: str) -> int:
        if not is_subject(subject):
            raise RevocationFailed("the subject is not id-shaped")
        entity = self._entity(subject)
        if entity is None:
            return 0
        disabled = self._post(f"/v1/identity/entity/id/{entity}", {"disabled": True})
        if disabled.status_code not in (200, 204):
            raise RevocationFailed(f"disabling the entity answered {disabled.status_code}")
        revoked = 0
        for accessor in self._accessors():
            if self._holder(accessor) != entity:
                continue
            response = self._post("/v1/auth/token/revoke-accessor", {"accessor": accessor})
            if response.status_code not in (200, 204):
                raise RevocationFailed(f"revoking a token answered {response.status_code}")
            revoked += 1
        return revoked
