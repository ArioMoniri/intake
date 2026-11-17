"""Keycloak's admin REST API behind :class:`~.directory.IdentityDirectory` (INT-366).

Seven calls, all documented Keycloak admin endpoints:

- ``POST /realms/<realm>/protocol/openid-connect/token`` — a client-credentials
  token for the confidential client the owner creates for this purpose
  (docs/runbooks/access-review.md names its realm-management roles);
- ``GET /admin/realms/<realm>/users`` (paged, full representation) and
  ``GET .../users/<id>`` — the accounts, their ``enabled`` flag, creation time
  and the ``tenant``/``org`` attributes the console's claims are mapped from;
- ``GET .../users/<id>/role-mappings/realm/composite`` — *effective* realm
  roles, so a role held through a group or a composite is reviewed too;
- ``GET .../events?type=LOGIN&user=<id>&max=1`` and ``GET .../events/config``
  — the last login, and whether the realm keeps enough login history for that
  answer to mean anything. Keycloak has no last-login field of its own;
- ``PUT .../users/<id>`` with ``{"enabled": false}`` and
  ``POST .../users/<id>/logout`` — the two writes offboarding makes.

**Nothing but ids leaves this module.** Keycloak answers with first and last
name and mail; none is copied (invariant 6). A username that is not id-shaped
is dropped too, because a realm that uses mail addresses as usernames would
otherwise put one on a page.

**Strict parsing.** An answer without the field the review depends on raises
:class:`~.directory.DirectoryUnavailable` rather than producing a holder with a
guessed role set or a guessed login.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Final

import httpx

from intake_platform.admin.access.directory import (
    STAFF_REALM_ROLES,
    DirectoryUnavailable,
    DirectoryUser,
    LoginHistoryUnavailable,
    RevocationFailed,
    is_subject,
)

__all__ = ["KeycloakAdminDirectory"]

_PAGE: Final = 100
_LOGIN: Final = "LOGIN"
_ID_SHAPE: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}")
_REALM_SHAPE: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")


def _instant(epoch_ms: object, what: str) -> datetime:
    if not isinstance(epoch_ms, int) or isinstance(epoch_ms, bool) or epoch_ms < 0:
        raise DirectoryUnavailable(f"{what} is not an epoch-millisecond integer")
    return datetime.fromtimestamp(epoch_ms / 1000, tz=UTC)


def _attribute(attributes: object, key: str) -> str | None:
    if not isinstance(attributes, Mapping):
        return None
    values = attributes.get(key)
    if not isinstance(values, list) or len(values) != 1:
        return None
    value = values[0]
    return value if isinstance(value, str) and _ID_SHAPE.fullmatch(value) else None


class KeycloakAdminDirectory:
    """:class:`~.directory.IdentityDirectory` over the Keycloak admin REST API."""

    def __init__(
        self, client: httpx.Client, *, realm: str, client_id: str, client_secret: str
    ) -> None:
        if not _REALM_SHAPE.fullmatch(realm):
            raise ValueError("the realm name is not id-shaped")
        self._client = client
        self._realm = realm
        self._client_id = client_id
        self._client_secret = client_secret
        self._token: str | None = None

    # -- transport -------------------------------------------------------------------

    def _fetch_token(self) -> str:
        try:
            response = self._client.post(
                f"/realms/{self._realm}/protocol/openid-connect/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                },
            )
            response.raise_for_status()
            token = response.json().get("access_token")
        except (httpx.HTTPError, ValueError) as err:
            raise DirectoryUnavailable(
                f"the admin client could not obtain a token ({type(err).__name__})"
            ) from None
        if not isinstance(token, str) or not token:
            raise DirectoryUnavailable("the token endpoint answered without an access token")
        return token

    def _send(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """One admin call with the service token; a 401 re-authenticates once
        (the token is short-lived by design) and then gives up."""
        for attempt in range(2):
            if self._token is None:
                self._token = self._fetch_token()
            response = self._client.request(
                method,
                f"/admin/realms/{self._realm}{path}",
                headers={"Authorization": f"Bearer {self._token}"},
                **kwargs,
            )
            if response.status_code == 401 and attempt == 0:
                self._token = None
                continue
            return response
        raise DirectoryUnavailable("the admin client is not authorised")

    def _read(self, path: str, **kwargs: Any) -> Any:
        try:
            response = self._send("GET", path, **kwargs)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as err:
            raise DirectoryUnavailable(f"a directory read failed ({type(err).__name__})") from None

    def _write(self, method: str, path: str, **kwargs: Any) -> None:
        try:
            response = self._send(method, path, **kwargs)
            response.raise_for_status()
        except (httpx.HTTPError, DirectoryUnavailable) as err:
            raise RevocationFailed(f"a directory write failed ({type(err).__name__})") from None

    # -- reads ------------------------------------------------------------------------

    def _roles(self, subject: str) -> frozenset[str]:
        payload = self._read(f"/users/{subject}/role-mappings/realm/composite")
        if not isinstance(payload, list):
            raise DirectoryUnavailable("the role mapping answer is not a list")
        names: set[str] = set()
        for role in payload:
            name = role.get("name") if isinstance(role, Mapping) else None
            if not isinstance(name, str):
                raise DirectoryUnavailable("a role mapping carries no name")
            names.add(name)
        return frozenset(names)

    def _last_login(self, subject: str) -> datetime | None:
        payload = self._read(
            "/events", params={"type": _LOGIN, "user": subject, "first": 0, "max": 1}
        )
        if not isinstance(payload, list):
            raise DirectoryUnavailable("the events answer is not a list")
        # Keycloak returns events newest first; taking the maximum over what
        # came back keeps the answer right if a store ever orders otherwise.
        stamps = [
            _instant(event.get("time"), "an event time")
            for event in payload
            if isinstance(event, Mapping) and event.get("type") == _LOGIN
        ]
        return max(stamps) if stamps else None

    def _user(self, raw: object, *, with_roles: frozenset[str] | None = None) -> DirectoryUser:
        if not isinstance(raw, Mapping):
            raise DirectoryUnavailable("a user representation is not an object")
        subject = raw.get("id")
        enabled = raw.get("enabled")
        if not is_subject(subject) or not isinstance(enabled, bool):
            raise DirectoryUnavailable("a user representation has no usable id or enabled flag")
        username = raw.get("username")
        roles = with_roles if with_roles is not None else self._roles(subject)
        return DirectoryUser(
            subject=subject,
            username=username
            if isinstance(username, str) and _ID_SHAPE.fullmatch(username)
            else None,
            enabled=enabled,
            realm_roles=roles,
            tenant=_attribute(raw.get("attributes"), "tenant"),
            org=_attribute(raw.get("attributes"), "org"),
            created_at=_instant(raw.get("createdTimestamp"), "a creation time"),
            last_login_at=self._last_login(subject) if roles & STAFF_REALM_ROLES else None,
        )

    def _pages(self) -> Sequence[Mapping[str, Any]]:
        users: list[Mapping[str, Any]] = []
        first = 0
        while True:
            page = self._read(
                "/users", params={"first": first, "max": _PAGE, "briefRepresentation": "false"}
            )
            if not isinstance(page, list):
                raise DirectoryUnavailable("the user list is not a list")
            users.extend(page)
            if len(page) < _PAGE:
                return users
            first += _PAGE

    def staff_users(self) -> list[DirectoryUser]:
        staff: list[DirectoryUser] = []
        for raw in self._pages():
            subject = raw.get("id") if isinstance(raw, Mapping) else None
            if not is_subject(subject):
                raise DirectoryUnavailable("a listed user has no usable id")
            roles = self._roles(subject)
            if roles & STAFF_REALM_ROLES:
                staff.append(self._user(raw, with_roles=roles))
        return sorted(staff, key=lambda user: user.subject)

    def user(self, subject: str) -> DirectoryUser | None:
        if not is_subject(subject):
            return None
        try:
            response = self._send("GET", f"/users/{subject}")
        except httpx.HTTPError as err:
            raise DirectoryUnavailable(f"a directory read failed ({type(err).__name__})") from None
        if response.status_code == 404:
            return None
        try:
            response.raise_for_status()
            raw = response.json()
        except (httpx.HTTPError, ValueError) as err:
            raise DirectoryUnavailable(f"a directory read failed ({type(err).__name__})") from None
        return self._user(raw)

    def login_history_days(self) -> float:
        config = self._read("/events/config")
        if not isinstance(config, Mapping) or config.get("eventsEnabled") is not True:
            raise LoginHistoryUnavailable("the realm does not record user events")
        types = config.get("enabledEventTypes")
        if not isinstance(types, list) or _LOGIN not in types:
            raise LoginHistoryUnavailable("the realm does not record LOGIN events")
        expiration = config.get("eventsExpiration")
        if expiration is None:
            return math.inf
        if not isinstance(expiration, int) or isinstance(expiration, bool) or expiration <= 0:
            raise LoginHistoryUnavailable("the realm's event expiry is not a positive integer")
        return expiration / 86_400

    # -- writes -----------------------------------------------------------------------

    def disable(self, subject: str) -> None:
        if not is_subject(subject):
            raise RevocationFailed("the subject is not id-shaped")
        self._write("PUT", f"/users/{subject}", json={"enabled": False})

    def revoke_sessions(self, subject: str) -> None:
        if not is_subject(subject):
            raise RevocationFailed("the subject is not id-shaped")
        self._write("POST", f"/users/{subject}/logout")
