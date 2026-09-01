"""The EHRbase (openEHR CDR) client — INT-032, the P3 export tier.

files/03 §7 names EHRbase the clinical core; ADR-002 and files/00 §3 D8
demote it to a P3 **export**, which is what this client serves. It speaks the
openEHR REST API (`/rest/openehr/v1`) and EHRbase's status endpoint, and
nothing else: no AQL, because no feature issues one.

Four rules this module keeps, each with a test in
``tests/platform/test_ehrbase_client.py``:

1. **The operational template reaches the wire byte-for-byte.** The bytes are
   the sha-pinned artefact ``protocols.bindings.openehr.OPT_PATH``, verified
   against ``OPT_SHA256`` by its loader before they ever get here. If the CDR
   refuses them, that is a finding to report, never a payload to repair —
   :class:`EhrbaseTemplateRejectedError` carries the server's own words out.
2. **Credentials come from OpenBao** (invariant 14). The base URL is not a
   secret and may come from the environment; the username and password may
   not, and :func:`ehrbase_config_from_env` reads them from the KV store or
   fails closed. Neither ever reaches ``repr``.
3. **Nothing logged can carry PHI** (invariant 6). Every log line is an event
   name, an id and a duration — the composition body is never logged, not
   even on a refusal, and a non-2xx response echoes the status and the
   server's message, never the request.
4. **Every failure is typed.** A transport error, a refusal and a
   well-formed-but-unusable response are three different things, and none of
   them is ``None``.

The EHRbase container is inside the deployment boundary and is addressed over
loopback in dev, so it adds no entry to
``infra/security/egress-allowlist.yaml`` and no PHI egress path.
"""

from __future__ import annotations

import base64
import logging
import time
import xml.etree.ElementTree as ElementTree  # noqa: S405
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final, Protocol

import httpx

__all__ = [
    "DEFAULT_TIMEOUT_S",
    "ENV_EHRBASE_URL",
    "OPENEHR_BASE_PATH",
    "SECRETS_KV_PATH",
    "STATUS_PATH",
    "CompositionVersion",
    "ContributionAudit",
    "EhrbaseClient",
    "EhrbaseConfig",
    "EhrbaseError",
    "EhrbaseNotConfiguredError",
    "EhrbaseRefusedError",
    "EhrbaseTemplateRejectedError",
    "EhrbaseUnavailableError",
    "KvSecrets",
    "ServerStatus",
    "TemplateState",
    "ehrbase_config_from_env",
]

logger = logging.getLogger("intake_platform.ehrbase")

DEFAULT_TIMEOUT_S: Final = 30.0
"""EHRbase pays for a Spring context and a jOOQ pool on its first request."""

ENV_EHRBASE_URL: Final = "INTAKE_EHRBASE_URL"
"""Where the CDR is. Not a secret; no default — a guessed CDR is a record
written somewhere nobody looked."""

SECRETS_KV_PATH: Final = "ehrbase"
"""KV v2 path under ``secret/`` holding ``{username, password}``."""

OPENEHR_BASE_PATH: Final = "/rest/openehr/v1"
STATUS_PATH: Final = "/rest/status"
_TEMPLATE_PATH: Final = f"{OPENEHR_BASE_PATH}/definition/template/adl1.4"


class EhrbaseError(RuntimeError):
    """Base for every failure this client raises."""


class EhrbaseNotConfiguredError(EhrbaseError):
    """No CDR address, or no credentials in the vault. Fails closed."""


class EhrbaseUnavailableError(EhrbaseError):
    """The CDR could not be reached at all (DNS, connect, read timeout)."""


class EhrbaseRefusedError(EhrbaseError):
    """The CDR answered, and said no. The request body is never echoed."""

    def __init__(self, status_code: int, operation: str, server_message: str) -> None:
        self.status_code: Final = status_code
        self.operation: Final = operation
        self.server_message: Final = server_message
        super().__init__(f"EHRbase refused {operation}: HTTP {status_code} — {server_message}")


class EhrbaseTemplateRejectedError(EhrbaseRefusedError):
    """The operational template was not accepted.

    Distinct from a plain refusal because the remedy is different in kind: an
    OPT the CDR will not parse is a defect in the committed template, to be
    reported and re-authored under review, never patched on the way to the
    wire (files/12 §8.1 — the sha pin exists so re-authoring forces a new
    questionnaire_definition version).
    """

    def __init__(self, status_code: int, template_id: str, server_message: str) -> None:
        super().__init__(status_code, f"template upload {template_id!r}", server_message)
        self.template_id: Final = template_id


class KvSecrets(Protocol):
    """The slice of ``intake_platform.secrets.SecretsProvider`` used here."""

    def get_kv(self, path: str) -> dict[str, Any]: ...


@dataclass(frozen=True)
class EhrbaseConfig:
    """Where the CDR is and how to authenticate to it."""

    base_url: str
    username: str
    password: str = field(repr=False)

    def __str__(self) -> str:
        return f"EhrbaseConfig(base_url={self.base_url!r}, username={self.username!r})"

    @property
    def basic_auth_header(self) -> str:
        raw = f"{self.username}:{self.password}".encode()
        return f"Basic {base64.b64encode(raw).decode('ascii')}"


def ehrbase_config_from_env(secrets: KvSecrets) -> EhrbaseConfig:
    """URL from the environment, credentials from OpenBao, both required."""
    import os

    base_url = os.environ.get(ENV_EHRBASE_URL, "").strip()
    if not base_url:
        raise EhrbaseNotConfiguredError(
            f"{ENV_EHRBASE_URL} is unset: the openEHR export has no CDR address and "
            "this client never guesses one"
        )
    bundle = secrets.get_kv(SECRETS_KV_PATH)
    missing = [key for key in ("username", "password") if not bundle.get(key)]
    if missing:
        raise EhrbaseNotConfiguredError(
            f"OpenBao secret/{SECRETS_KV_PATH} is missing {', '.join(missing)} — EHRbase "
            "credentials come from the vault only (invariant 14), never from the "
            "environment"
        )
    return EhrbaseConfig(
        base_url=base_url, username=str(bundle["username"]), password=str(bundle["password"])
    )


@dataclass(frozen=True)
class ServerStatus:
    """What ``/rest/status`` reports. Used by the roundtrip and the probe."""

    ehrbase_version: str
    openehr_sdk_version: str


@dataclass(frozen=True)
class TemplateState:
    """Whether this boot uploaded the template or found it already there."""

    template_id: str
    uploaded: bool


@dataclass(frozen=True)
class CompositionVersion:
    """A committed composition's version, split so callers never re-parse the uid."""

    version_uid: str
    object_id: str
    version: int


@dataclass(frozen=True)
class ContributionAudit:
    """The CONTRIBUTION a write landed in (INT-032 acceptance: contribution audit)."""

    contribution_id: str
    change_type: str
    committer: str | None
    time_committed: str | None
    version_uids: tuple[str, ...]


class EhrbaseClient:
    """A small, synchronous openEHR REST client.

    ``transport`` is the seam: tests pass ``httpx.MockTransport`` and a
    deployment can pass ``intake_platform.egress.guarded_transport``.
    """

    def __init__(
        self,
        config: EhrbaseConfig,
        *,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._config = config
        self._timeout_s = timeout_s
        self._transport = transport

    # --- transport -----------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        operation: str,
        headers: Mapping[str, str] | None = None,
        content: bytes | None = None,
        json_body: Any = None,
        expected: tuple[int, ...] = (200,),
        tolerated: tuple[int, ...] = (),
    ) -> httpx.Response:
        merged = {"Authorization": self._config.basic_auth_header}
        merged.update(headers or {})
        started = time.monotonic()
        try:
            with httpx.Client(
                base_url=self._config.base_url,
                timeout=self._timeout_s,
                transport=self._transport,
            ) as client:
                response = client.request(
                    method, path, headers=merged, content=content, json=json_body
                )
        except httpx.HTTPError as exc:
            # The exception text is httpx's own (a host and a reason), never ours.
            logger.warning(
                "ehrbase call failed", extra={"event": operation, "duration_ms": _ms(started)}
            )
            raise EhrbaseUnavailableError(f"EHRbase unreachable for {operation}: {exc}") from exc
        logger.debug("ehrbase call", extra={"event": operation, "duration_ms": _ms(started)})
        if response.status_code in expected or response.status_code in tolerated:
            return response
        raise EhrbaseRefusedError(response.status_code, operation, _server_message(response))

    # --- server --------------------------------------------------------------

    def status(self) -> ServerStatus:
        response = self._request("GET", STATUS_PATH, operation="status")
        try:
            root = ElementTree.fromstring(response.content)  # noqa: S314
        except ElementTree.ParseError as exc:
            raise EhrbaseRefusedError(
                response.status_code, "status", f"unparseable status document: {exc}"
            ) from exc
        return ServerStatus(
            ehrbase_version=_child_text(root, "ehrbase_version"),
            openehr_sdk_version=_child_text(root, "openehr_sdk_version"),
        )

    # --- operational template ------------------------------------------------

    def ensure_template(self, opt_xml: bytes, *, template_id: str) -> TemplateState:
        """Upload the pinned template, idempotently. The bytes are not touched."""
        try:
            response = self._request(
                "POST",
                _TEMPLATE_PATH,
                operation=f"template upload {template_id!r}",
                headers={"Content-Type": "application/xml", "Accept": "application/xml"},
                content=opt_xml,
                expected=(200, 201),
                tolerated=(409,),
            )
        except EhrbaseRefusedError as refusal:
            # Narrowed on purpose: the remedy for a rejected OPT is to re-author
            # the committed template under review, not to retry or to patch.
            raise EhrbaseTemplateRejectedError(
                refusal.status_code, template_id, refusal.server_message
            ) from refusal
        if response.status_code == 409:
            return TemplateState(template_id=template_id, uploaded=False)
        return TemplateState(template_id=template_id, uploaded=True)

    def get_template(self, template_id: str) -> bytes:
        """The template as the CDR stored it — re-serialised, so parse, never diff."""
        response = self._request(
            "GET",
            f"{_TEMPLATE_PATH}/{template_id}",
            operation=f"template fetch {template_id!r}",
            headers={"Accept": "application/xml"},
        )
        return response.content

    # --- ehr -----------------------------------------------------------------

    def create_ehr(self, ehr_status: Mapping[str, Any]) -> str:
        response = self._request(
            "POST",
            f"{OPENEHR_BASE_PATH}/ehr",
            operation="ehr create",
            headers={"Prefer": "return=representation", "Accept": "application/json"},
            json_body=dict(ehr_status),
            expected=(200, 201),
        )
        ehr_id = _json_path(response, "ehr create", "ehr_id", "value")
        return str(ehr_id)

    def get_ehr_status(self, ehr_id: str) -> dict[str, Any]:
        response = self._request(
            "GET",
            f"{OPENEHR_BASE_PATH}/ehr/{ehr_id}/ehr_status",
            operation="ehr_status fetch",
            headers={"Accept": "application/json"},
        )
        return _json_object(response, "ehr_status fetch")

    # --- composition ---------------------------------------------------------

    def write_composition(self, ehr_id: str, composition: Mapping[str, Any]) -> CompositionVersion:
        response = self._request(
            "POST",
            f"{OPENEHR_BASE_PATH}/ehr/{ehr_id}/composition",
            operation="composition write",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Prefer": "return=representation",
            },
            json_body=dict(composition),
            expected=(200, 201),
        )
        version_uid = str(_json_path(response, "composition write", "uid", "value"))
        return _split_version_uid(version_uid)

    def read_composition(self, ehr_id: str, version_uid: str) -> dict[str, Any]:
        response = self._request(
            "GET",
            f"{OPENEHR_BASE_PATH}/ehr/{ehr_id}/composition/{version_uid}",
            operation="composition read",
            headers={"Accept": "application/json"},
        )
        return _json_object(response, "composition read")

    # --- contribution audit ---------------------------------------------------

    def contribution(self, ehr_id: str, version_uid: str) -> ContributionAudit:
        """The CONTRIBUTION a composition version was committed in, with its audit."""
        object_id = _split_version_uid(version_uid).object_id
        version = _json_object(
            self._request(
                "GET",
                f"{OPENEHR_BASE_PATH}/ehr/{ehr_id}/versioned_composition/{object_id}"
                f"/version/{version_uid}",
                operation="versioned composition read",
                headers={"Accept": "application/json"},
            ),
            "versioned composition read",
        )
        contribution_id = str(
            _nested(version, "versioned composition read", "contribution", "id", "value")
        )
        audit = version.get("commit_audit")
        if not isinstance(audit, Mapping):
            raise EhrbaseRefusedError(
                200, "versioned composition read", "version carries no commit_audit"
            )
        committer = audit.get("committer")
        contribution = _json_object(
            self._request(
                "GET",
                f"{OPENEHR_BASE_PATH}/ehr/{ehr_id}/contribution/{contribution_id}",
                operation="contribution read",
                headers={"Accept": "application/json"},
            ),
            "contribution read",
        )
        versions = contribution.get("versions")
        uids: tuple[str, ...] = ()
        if isinstance(versions, list):
            uids = tuple(
                str(entry["id"]["value"])
                for entry in versions
                if isinstance(entry, Mapping) and isinstance(entry.get("id"), Mapping)
            )
        return ContributionAudit(
            contribution_id=contribution_id,
            change_type=str(_nested(audit, "versioned composition read", "change_type", "value")),
            committer=str(committer["name"]) if isinstance(committer, Mapping) else None,
            time_committed=(
                str(audit["time_committed"]["value"])
                if isinstance(audit.get("time_committed"), Mapping)
                else None
            ),
            version_uids=uids,
        )


# --- helpers --------------------------------------------------------------------


def _ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _server_message(response: httpx.Response) -> str:
    """The server's own words, truncated. Never the request we sent."""
    try:
        payload = response.json()
    except ValueError:
        return response.text.strip()[:200]
    if isinstance(payload, Mapping):
        for key in ("message", "error", "detail"):
            value = payload.get(key)
            if isinstance(value, str):
                return value[:200]
    return response.text.strip()[:200]


def _json_object(response: httpx.Response, operation: str) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise EhrbaseRefusedError(
            response.status_code, operation, f"response is not JSON: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise EhrbaseRefusedError(response.status_code, operation, "response is not a JSON object")
    return payload


def _json_path(response: httpx.Response, operation: str, *path: str) -> Any:
    return _nested(_json_object(response, operation), operation, *path)


def _nested(payload: Mapping[str, Any], operation: str, *path: str) -> Any:
    cursor: Any = payload
    for step in path:
        if not isinstance(cursor, Mapping) or step not in cursor:
            raise EhrbaseRefusedError(200, operation, f"response carries no {'/'.join(path)}")
        cursor = cursor[step]
    return cursor


def _split_version_uid(version_uid: str) -> CompositionVersion:
    """``<object id>::<system id>::<version>`` — the openEHR OBJECT_VERSION_ID."""
    parts = version_uid.split("::")
    if len(parts) != 3 or not parts[2].isdigit():
        raise EhrbaseRefusedError(
            200,
            "composition write",
            f"version uid {version_uid!r} is not <object_id>::<system_id>::<version>",
        )
    return CompositionVersion(version_uid=version_uid, object_id=parts[0], version=int(parts[2]))


def _child_text(root: ElementTree.Element, tag: str) -> str:
    child = root.find(tag)
    if child is None or child.text is None:
        raise EhrbaseRefusedError(200, "status", f"status document has no <{tag}>")
    return child.text.strip()
