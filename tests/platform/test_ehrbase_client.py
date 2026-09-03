"""INT-032 — the EHRbase client contract, without a container.

``tests/integration/test_ehrbase_roundtrip.py`` proves the client against a
real CDR. This lane proves the parts a live server would not exercise
reliably: that configuration comes from OpenBao and fails closed without it,
that every non-2xx becomes a typed refusal rather than a silent ``None``, that
the pinned operational template is never patched on its way to the wire, and
that nothing the client logs can carry PHI (invariant 6).

Every request here is served by ``httpx.MockTransport`` — the same seam the
egress guard uses — so no socket opens.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx
import pytest
from intake_platform.ehrbase import (
    ENV_EHRBASE_URL,
    CompositionVersion,
    EhrbaseClient,
    EhrbaseConfig,
    EhrbaseNotConfiguredError,
    EhrbaseRefusedError,
    EhrbaseTemplateRejectedError,
    EhrbaseUnavailableError,
    ehrbase_config_from_env,
)

BASE_URL = "http://ehrbase.invalid:8080/ehrbase"
TEMPLATE_ID = "previsit_intake.v1"
OPT_XML = (
    b'<?xml version="1.0"?><template>'
    b"<template_id><value>previsit_intake.v1</value></template_id></template>"
)
EHR_ID = "bc389e58-02f4-4b0f-9304-72dfee6cc82a"
VERSION_UID = "1958c9f2-3245-40c7-b624-3082852a1939::local.ehrbase.org::1"


def _config() -> EhrbaseConfig:
    return EhrbaseConfig(base_url=BASE_URL, username="intake", password="intake-dev-only")


def _client(handler: Any) -> EhrbaseClient:
    return EhrbaseClient(_config(), transport=httpx.MockTransport(handler))


# --- configuration fails closed ---------------------------------------------------


def test_config_from_env_needs_the_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_EHRBASE_URL, raising=False)
    with pytest.raises(EhrbaseNotConfiguredError, match=ENV_EHRBASE_URL):
        ehrbase_config_from_env(_StubSecrets({"username": "u", "password": "p"}))


def test_config_reads_credentials_from_openbao_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """invariant 14: secrets only from OpenBao. The URL is not a secret and may
    come from the environment; the credentials may not."""
    monkeypatch.setenv(ENV_EHRBASE_URL, BASE_URL)
    monkeypatch.setenv("EHRBASE_PASSWORD", "from-the-environment")
    config = ehrbase_config_from_env(_StubSecrets({"username": "u", "password": "from-bao"}))
    assert config.password == "from-bao"


def test_config_refuses_a_secret_bundle_missing_a_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ENV_EHRBASE_URL, BASE_URL)
    with pytest.raises(EhrbaseNotConfiguredError, match="password"):
        ehrbase_config_from_env(_StubSecrets({"username": "u"}))


def test_the_password_never_reaches_repr_or_str() -> None:
    config = _config()
    assert "intake-dev-only" not in repr(config)
    assert "intake-dev-only" not in str(config)


class _StubSecrets:
    """The narrow slice of ``SecretsProvider`` the client needs."""

    def __init__(self, payload: dict[str, str]) -> None:
        self._payload = payload

    def get_kv(self, path: str) -> dict[str, Any]:
        assert path == "ehrbase"
        return dict(self._payload)


# --- template: uploaded verbatim, never patched -----------------------------------


def test_ensure_template_posts_the_bytes_verbatim() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = request.content
        seen["content_type"] = request.headers["Content-Type"]
        seen["auth"] = request.headers.get("Authorization", "")
        return httpx.Response(201, text="")

    state = _client(handler).ensure_template(OPT_XML, template_id=TEMPLATE_ID)
    assert state.uploaded is True
    assert state.template_id == TEMPLATE_ID
    assert seen["body"] == OPT_XML, "the pinned template must reach the CDR byte-for-byte"
    assert seen["url"].endswith("/rest/openehr/v1/definition/template/adl1.4")
    assert seen["content_type"] == "application/xml"
    assert seen["auth"].startswith("Basic ")


def test_ensure_template_treats_conflict_as_already_present() -> None:
    state = _client(lambda request: httpx.Response(409, text="duplicate")).ensure_template(
        OPT_XML, template_id=TEMPLATE_ID
    )
    assert state.uploaded is False
    assert state.template_id == TEMPLATE_ID


def test_a_rejected_template_raises_and_carries_the_servers_own_words() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="<error>Internal Server Error</error>")

    with pytest.raises(EhrbaseTemplateRejectedError) as excinfo:
        _client(handler).ensure_template(OPT_XML, template_id=TEMPLATE_ID)
    assert excinfo.value.status_code == 500
    assert "Internal Server Error" in excinfo.value.server_message
    assert TEMPLATE_ID in str(excinfo.value)


def test_get_template_returns_the_xml_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith(f"/definition/template/adl1.4/{TEMPLATE_ID}")
        assert request.headers["Accept"] == "application/xml"
        return httpx.Response(200, content=OPT_XML)

    assert _client(handler).get_template(TEMPLATE_ID) == OPT_XML


# --- ehr, composition, contribution -----------------------------------------------


def test_create_ehr_returns_the_ehr_id() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path.endswith("/rest/openehr/v1/ehr")
        return httpx.Response(201, json={"ehr_id": {"value": EHR_ID}})

    assert _client(handler).create_ehr({"_type": "EHR_STATUS"}) == EHR_ID


def test_write_composition_returns_the_version_uid_split_into_its_parts() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Prefer"] == "return=representation"
        return httpx.Response(201, json={"uid": {"value": VERSION_UID}})

    version = _client(handler).write_composition(EHR_ID, {"_type": "COMPOSITION"})
    assert version == CompositionVersion(
        version_uid=VERSION_UID,
        object_id="1958c9f2-3245-40c7-b624-3082852a1939",
        version=1,
    )


def test_a_composition_response_without_a_uid_is_a_refusal_not_a_none() -> None:
    with pytest.raises(EhrbaseRefusedError, match="uid"):
        _client(lambda request: httpx.Response(201, json={})).write_composition(
            EHR_ID, {"_type": "COMPOSITION"}
        )


def test_read_composition_returns_the_canonical_json() -> None:
    body = {"_type": "COMPOSITION", "archetype_node_id": "openEHR-EHR-COMPOSITION.x.v1"}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith(f"/ehr/{EHR_ID}/composition/{VERSION_UID}")
        return httpx.Response(200, json=body)

    assert _client(handler).read_composition(EHR_ID, VERSION_UID) == body


def test_contribution_audit_is_read_from_the_versioned_object() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "/versioned_composition/" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "contribution": {"id": {"value": "81e9e56b-bf8e-4fcd-a218-270ba0baa8c2"}},
                    "commit_audit": {
                        "change_type": {"value": "creation"},
                        "time_committed": {"value": "2026-08-29T16:08:52.128537Z"},
                        "committer": {"name": "INTAKE"},
                    },
                },
            )
        return httpx.Response(
            200,
            json={
                "uid": {"value": "81e9e56b-bf8e-4fcd-a218-270ba0baa8c2"},
                "versions": [{"id": {"value": VERSION_UID}}],
            },
        )

    audit = _client(handler).contribution(EHR_ID, VERSION_UID)
    assert audit.contribution_id == "81e9e56b-bf8e-4fcd-a218-270ba0baa8c2"
    assert audit.change_type == "creation"
    assert audit.committer == "INTAKE"
    assert audit.version_uids == (VERSION_UID,)


# --- errors are typed, and never leak the payload ---------------------------------


def test_a_transport_failure_becomes_ehrbase_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(EhrbaseUnavailableError):
        _client(handler).status()


def test_a_4xx_on_a_composition_write_does_not_echo_the_composition() -> None:
    composition = {"_type": "COMPOSITION", "narrative": "göğsümde baskı var"}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"message": "Bad Request"})

    with pytest.raises(EhrbaseRefusedError) as excinfo:
        _client(handler).write_composition(EHR_ID, composition)
    assert "göğsümde" not in str(excinfo.value)
    assert excinfo.value.status_code == 400


def test_nothing_the_client_logs_carries_clinical_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """invariant 6: ids and durations only. A Turkish symptom sentence is
    planted in the payload; no log record may repeat it."""
    sentinel = "göğsümde baskı var"
    composition = {"_type": "COMPOSITION", "narrative": sentinel}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={"uid": {"value": VERSION_UID}})

    with caplog.at_level(logging.DEBUG, logger="intake_platform.ehrbase"):
        _client(handler).write_composition(EHR_ID, composition)
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert sentinel not in text
    assert json.dumps(composition, ensure_ascii=False) not in text


def test_status_reports_the_server_version() -> None:
    xml = (
        b"<status><ehrbase_version>2.35.1</ehrbase_version>"
        b"<openehr_sdk_version>2.35.0</openehr_sdk_version></status>"
    )
    status = _client(lambda request: httpx.Response(200, content=xml)).status()
    assert status.ehrbase_version == "2.35.1"
    assert status.openehr_sdk_version == "2.35.0"


def test_status_refuses_a_status_document_that_declares_entities() -> None:
    """A server response is data, never instructions (CLAUDE.md invariant 14).

    The stdlib parser expands internally declared entities: the document below
    turns one declaration into a 10x expansion, and nesting it is the classic
    billion-laughs allocation attack. A hostile or compromised CDR is exactly
    the threat the openEHR boundary exists to contain, so the parse must refuse
    the DTD rather than expand it — and refuse as a typed EhrbaseRefusedError,
    not as whatever the parser happens to throw.
    """
    xml = (
        b'<?xml version="1.0"?>'
        b'<!DOCTYPE status [<!ENTITY a "lol">'
        b'<!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">]>'
        b"<status><ehrbase_version>&b;</ehrbase_version>"
        b"<openehr_sdk_version>2.35.0</openehr_sdk_version></status>"
    )
    with pytest.raises(EhrbaseRefusedError):
        _client(lambda request: httpx.Response(200, content=xml)).status()
