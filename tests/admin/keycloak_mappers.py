"""What a Keycloak 26.1.4 access token carries, given a realm export (INT-373).

No test dials Keycloak and there is no container runtime to start one. So this
module reproduces, for the three mapper types the committed realm uses, the
exact rule Keycloak applies when it builds an access token. Each rule is cited
to the source at the tag ``infra/docker-compose.obs.yml`` pins:

- **gate** — ``AbstractOIDCProtocolMapper.transformAccessToken``: a mapper
  touches the access token only when ``access.token.claim`` is the string
  ``"true"`` (``OIDCAttributeMapperHelper.includeInAccessToken``).
- ``oidc-audience-mapper`` — ``AudienceProtocolMapper.setClaim``: adds
  ``included.client.audience``, else ``included.custom.audience``, to ``aud``.
  ``JsonWebToken.aud`` serialises one audience as a string and several as an
  array (``StringOrArraySerializer``).
- ``oidc-usermodel-attribute-mapper`` — ``UserAttributeMapper.setClaim`` via
  ``KeycloakModelUtils.resolveAttribute``: the user's own values. (Keycloak falls
  back to a group attribute when the user has none. That fallback is not
  modelled here, and the runbook says to set these on the user.)
- ``oidc-usersessionmodel-note-mapper`` — ``UserSessionNoteMapper.setClaim``:
  ``userSession.getNote(user.session.note)``; no note, no claim.
- **value shaping** — ``OIDCAttributeMapperHelper.mapAttributeValue``: an empty
  value is no claim; not ``multivalued`` takes the first value; ``multivalued``
  keeps a list; ``jsonType.label`` converts (``String``, ``int``/``long``,
  ``boolean``, ``JSON``). ``claim.name`` is split on unescaped dots into
  nested objects (``JsonUtils.splitClaimPath``).

A mapper of any other type is skipped: this model does not own it. The claims
it does not produce — ``iss``, ``sub``, ``sid``, ``realm_access``, ``amr`` —
come from Keycloak's built-in scopes and ``TokenManager``, and the caller
passes them in as ``base``.
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

__all__ = [
    "AUDIENCE_MAPPER",
    "NOTE_MAPPER",
    "USER_ATTRIBUTE_MAPPER",
    "client",
    "mint_access_token_claims",
]

AUDIENCE_MAPPER = "oidc-audience-mapper"
USER_ATTRIBUTE_MAPPER = "oidc-usermodel-attribute-mapper"
NOTE_MAPPER = "oidc-usersessionmodel-note-mapper"

_UNESCAPED_DOT = re.compile(r"(?<!\\)\.")


def client(realm: Mapping[str, Any], client_id: str) -> dict[str, Any]:
    matches = [c for c in realm["clients"] if c["clientId"] == client_id]
    assert len(matches) == 1, f"the realm declares {len(matches)} clients named {client_id!r}"
    found: dict[str, Any] = matches[0]
    return found


def _claim_path(name: str) -> list[str]:
    return [part.replace("\\.", ".") for part in _UNESCAPED_DOT.split(name) if part]


def _typed(json_type: str | None, value: str) -> Any:
    if json_type is None or json_type == "String":
        return value
    if json_type in ("int", "long"):
        return int(value)
    if json_type == "boolean":
        return value.lower() == "true"
    if json_type == "JSON":
        return json.loads(value)
    return value


def _shaped(config: Mapping[str, str], values: Sequence[str] | None) -> Any:
    if not values:
        return None
    json_type = config.get("jsonType.label")
    if config.get("multivalued") == "true":
        return [_typed(json_type, v) for v in values]
    return _typed(json_type, values[0])


def _put(claims: dict[str, Any], name: str | None, value: Any) -> None:
    if value is None or not name:
        return
    path = _claim_path(name)
    if not path:
        return
    node = claims
    for part in path[:-1]:
        node = node.setdefault(part, {})
    node[path[-1]] = value


def mint_access_token_claims(
    realm: Mapping[str, Any],
    client_id: str,
    *,
    base: Mapping[str, Any],
    user_attributes: Mapping[str, Sequence[str]],
    session_notes: Mapping[str, str],
) -> dict[str, Any]:
    """The access-token claims Keycloak would issue to ``client_id``."""
    claims = {k: copy.deepcopy(v) for k, v in base.items()}
    audiences: list[str] = []
    for mapper in client(realm, client_id).get("protocolMappers", []):
        config: Mapping[str, str] = mapper.get("config", {})
        if mapper.get("protocol") != "openid-connect":
            continue
        if config.get("access.token.claim") != "true":
            continue
        kind = mapper.get("protocolMapper")
        if kind == AUDIENCE_MAPPER:
            audience = config.get("included.client.audience") or config.get(
                "included.custom.audience"
            )
            if audience:
                audiences.append(audience)
        elif kind == USER_ATTRIBUTE_MAPPER:
            values = user_attributes.get(config.get("user.attribute", ""))
            _put(claims, config.get("claim.name"), _shaped(config, values))
        elif kind == NOTE_MAPPER:
            note = session_notes.get(config.get("user.session.note", ""))
            _put(
                claims, config.get("claim.name"), _shaped(config, None if note is None else [note])
            )
    if audiences:
        claims["aud"] = audiences[0] if len(audiences) == 1 else audiences
    return claims
