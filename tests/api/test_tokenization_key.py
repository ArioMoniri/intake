"""INT-584 (owner decision D38) — the phone-tokenization key comes from OpenBao alone.

Until INT-584 the synthetic host kept the HMAC key every phone pseudonym is
derived under in its root-only env file, and ``ApiSettings.from_env`` read it
from ``INTAKE_TOKENIZATION_KEY``. D38 moves it to OpenBao ``secret/api/tokenization``
with the same key material, so no pseudonym changes. Pinned here, each with a
near miss:

- the environment is never read for the key, in any environment, and a key in
  the environment is never a fallback when OpenBao has none;
- the same key material gives the same pseudonym it gave on the env path —
  the key is the hex TEXT's UTF-8 bytes, never hex-decoded, and a key one
  character away gives another pseudonym;
- absent, unreadable and malformed are told apart, each leaves the OTP tier and
  the previsit read-back at 503 with that typed reason, and none prints a value;
- dev under file-dev KEKs alone takes a process-local key and reads no vault;
- ``tokenization_key_state{state,origin}`` says which, with ids only.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import httpx
import pytest
from api_harness import ADMIN_TOKEN, PATIENT_TOKEN, build_harness
from intake_api.dev_fixture import DEV_TENANT_ID
from intake_api.settings import ENV_TOKENIZATION_KEY, ApiSettings
from intake_api.state import _tokenizer_from_settings
from intake_api.tokenization_key import (
    TOKENIZATION_KV_PATH,
    TokenizationKeyOrigin,
    TokenizationKeyResolution,
    TokenizationKeyState,
    resolve_tokenization_key,
    with_tokenization_key,
)
from intake_platform.secrets import SecretsBootError
from intake_platform.tokenization import Tokenizer
from prometheus_client import REGISTRY

# Synthetic key material only: 64 lower-case hex characters, the shape
# lib.sh's gen_secret wrote into the synthetic host's env file.
KEY = "3f" * 8 + "a1" * 8 + "0c" * 8 + "e7" * 8
#: One character away: the near miss every equality claim is held against.
NEAR_KEY = KEY[:-1] + ("0" if KEY[-1] != "0" else "1")
#: A synthetic subscriber number; it never leaves the test.
NUMBER = "+905550000001"


class Vault:
    """A stand-in OpenBao KV reader that records every path it is asked for."""

    def __init__(
        self, documents: dict[str, dict[str, Any]] | None = None, error: Exception | None = None
    ) -> None:
        self.documents = documents or {}
        self.error = error
        self.paths: list[str] = []

    def get_kv(self, path: str) -> dict[str, Any]:
        self.paths.append(path)
        if self.error is not None:
            raise self.error
        if path not in self.documents:
            raise _status(404)
        return dict(self.documents[path])


def _status(code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", f"http://openbao:8200/v1/secret/data/{TOKENIZATION_KV_PATH}")
    return httpx.HTTPStatusError("refused", request=request, response=httpx.Response(code))


def _settings(environment: str = "staging", kek_mode: str = "transit") -> ApiSettings:
    return ApiSettings(
        token_patient=None,
        token_admin=None,
        app_db_url="postgresql+psycopg://app_rw@db.internal:5432/intake",
        audit_db_url="postgresql+psycopg://svc_audit_writer@db.internal:5432/intake",
        bootstrap_db_url="postgresql+psycopg://intake_owner@db.internal:5432/intake",
        kek_mode=kek_mode,  # type: ignore[arg-type]
        environment=environment,
    )


def _migrated(key: str = KEY, origin: str = "env_file") -> Vault:
    return Vault({TOKENIZATION_KV_PATH: {"key": key, "origin": origin}})


def _env_path_pseudonym(key: str, number: str = NUMBER) -> str:
    """What the API derived before D38: ``settings.tokenization_key`` was the
    env string, and every Tokenizer took its UTF-8 bytes under key id v1."""
    return Tokenizer(keys={"v1": key.encode("utf-8")}, active_key_id="v1").pseudonym(number)


def _gauge(state: str, origin: str) -> float | None:
    return REGISTRY.get_sample_value("tokenization_key_state", {"state": state, "origin": origin})


# --- the environment is never the source --------------------------------------------


@pytest.mark.parametrize("environment", ["dev", "staging", "prod"])
def test_from_env_never_reads_the_key_from_the_environment(
    monkeypatch: pytest.MonkeyPatch, environment: str
) -> None:
    monkeypatch.setenv(ENV_TOKENIZATION_KEY, KEY)
    monkeypatch.setenv("INTAKE_ENV", environment)
    for name in (
        "INTAKE_API_DB_URL",
        "INTAKE_API_AUDIT_DB_URL",
        "INTAKE_API_BOOTSTRAP_DB_URL",
        "MINIO_ROOT_USER",
        "MINIO_ROOT_PASSWORD",
    ):
        monkeypatch.setenv(name, "set-for-the-strict-boot")
    settings = ApiSettings.from_env()
    assert settings.tokenization_key is None
    assert settings.otp_auth_configured is False


def test_a_key_in_the_environment_is_no_fallback_on_the_synthetic_host(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The near miss for "OpenBao only": the old env value is right there, and
    OpenBao has nothing — the tier stays shut rather than reach for it."""
    monkeypatch.setenv(ENV_TOKENIZATION_KEY, KEY)
    caplog.set_level(logging.INFO)
    settings = with_tokenization_key(_settings("staging"), Vault())
    assert settings.tokenization_key is None
    assert settings.tokenization_key_refusal == "tokenization_key_absent"
    assert ENV_TOKENIZATION_KEY in caplog.text, "the stray variable is named"
    assert KEY not in caplog.text and KEY[:16] not in caplog.text


# --- the same key material, the same pseudonyms ----------------------------------------


def test_the_key_is_read_from_secret_api_tokenization() -> None:
    vault = _migrated()
    resolution = resolve_tokenization_key(_settings(), vault)
    assert vault.paths == [TOKENIZATION_KV_PATH] == ["api/tokenization"]
    assert resolution.state is TokenizationKeyState.LOADED
    assert resolution.origin is TokenizationKeyOrigin.ENV_FILE
    assert resolution.key == KEY
    assert resolution.refusal is None


def test_the_migrated_key_gives_every_pseudonym_it_gave_from_the_env_file() -> None:
    """D38's whole claim: carrying the material across changes no pseudonym,
    through the very Tokenizer construction the API uses."""
    settings = with_tokenization_key(_settings(), _migrated())
    tokenizer = _tokenizer_from_settings(settings)
    assert tokenizer is not None
    for number in (NUMBER, "+905550000002", "0555 000 00 03"):
        assert tokenizer.pseudonym(number) == _env_path_pseudonym(KEY, number)


def test_near_miss_a_decoded_or_neighbouring_key_forks_the_pseudonym() -> None:
    """Why the module must not "improve" the key: hex-decoding it, or one
    character of drift, would give every patient a new pseudonym."""
    before = _env_path_pseudonym(KEY)
    decoded = Tokenizer(keys={"v1": bytes.fromhex(KEY)}, active_key_id="v1").pseudonym(NUMBER)
    assert decoded != before
    assert _env_path_pseudonym(NEAR_KEY) != before
    settings = with_tokenization_key(_settings(), _migrated(NEAR_KEY))
    tokenizer = _tokenizer_from_settings(settings)
    assert tokenizer is not None and tokenizer.pseudonym(NUMBER) != before


@pytest.mark.parametrize(
    ("origin", "expected"),
    [
        ("env_file", TokenizationKeyOrigin.ENV_FILE),
        ("generated", TokenizationKeyOrigin.GENERATED),
        ("process_local", TokenizationKeyOrigin.UNRECORDED),
        ("something-else", TokenizationKeyOrigin.UNRECORDED),
        (None, TokenizationKeyOrigin.UNRECORDED),
    ],
)
def test_the_origin_is_a_closed_vocabulary(
    origin: str | None, expected: TokenizationKeyOrigin
) -> None:
    document: dict[str, Any] = {"key": KEY}
    if origin is not None:
        document["origin"] = origin
    resolution = resolve_tokenization_key(_settings(), Vault({TOKENIZATION_KV_PATH: document}))
    assert resolution.state is TokenizationKeyState.LOADED
    assert resolution.origin is expected


# --- absent, unreadable, malformed: told apart, fail closed ----------------------------


@pytest.mark.parametrize(
    ("vault", "state"),
    [
        (Vault(), TokenizationKeyState.ABSENT),
        (Vault({TOKENIZATION_KV_PATH: {}}), TokenizationKeyState.ABSENT),
        (Vault({TOKENIZATION_KV_PATH: {"key": "   "}}), TokenizationKeyState.ABSENT),
        (Vault(error=_status(403)), TokenizationKeyState.UNREADABLE),
        (Vault(error=_status(503)), TokenizationKeyState.UNREADABLE),
        (Vault(error=httpx.ConnectError("refused")), TokenizationKeyState.UNREADABLE),
        (Vault(error=SecretsBootError("no token")), TokenizationKeyState.UNREADABLE),
        (Vault({TOKENIZATION_KV_PATH: {"key": "ab" * 8}}), TokenizationKeyState.MALFORMED),
        (Vault({TOKENIZATION_KV_PATH: {"key": KEY.upper()}}), TokenizationKeyState.MALFORMED),
        (Vault({TOKENIZATION_KV_PATH: {"key": "zz" * 32}}), TokenizationKeyState.MALFORMED),
        (Vault({TOKENIZATION_KV_PATH: {"key": KEY + " "}}), TokenizationKeyState.MALFORMED),
        (Vault({TOKENIZATION_KV_PATH: {"key": 7}}), TokenizationKeyState.MALFORMED),
    ],
    ids=[
        "no-document",
        "empty-document",
        "blank-key",
        "policy-refuses",
        "sealed",
        "unreachable",
        "no-openbao-token",
        "short",
        "upper-case",
        "not-hex",
        "trailing-space",
        "not-a-string",
    ],
)
def test_every_failure_has_its_typed_reason_and_no_key(
    vault: Vault, state: TokenizationKeyState, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    settings = with_tokenization_key(_settings(), vault)
    assert settings.tokenization_key is None
    assert settings.otp_auth_configured is False
    assert _tokenizer_from_settings(settings) is None
    assert settings.tokenization_key_refusal == f"tokenization_key_{state.value}"
    assert _gauge(state.value, "none") == 1.0
    assert f"secret/{TOKENIZATION_KV_PATH}" in caplog.text
    assert KEY not in caplog.text and KEY.upper() not in caplog.text


def test_a_loaded_key_carries_no_refusal_and_the_gauge_moves_with_it() -> None:
    """The gauge holds one series at 1: a later resolution clears the last."""
    with_tokenization_key(_settings(), Vault())
    assert _gauge("absent", "none") == 1.0
    settings = with_tokenization_key(_settings(), _migrated())
    assert settings.tokenization_key == KEY
    assert settings.tokenization_key_refusal is None
    assert _gauge("loaded", "env_file") == 1.0
    assert _gauge("absent", "none") is None


def test_a_settings_object_built_with_a_key_carries_no_refusal() -> None:
    """The test harnesses construct settings directly: a key means no reason,
    no key and no reason means absent."""
    with_key = replace(_settings(), tokenization_key=KEY)
    assert with_key.tokenization_key_refusal is None
    assert _settings().tokenization_key_refusal == "tokenization_key_absent"
    stale = replace(_settings(), tokenization_key_refusal="tokenization_key_unreadable")
    assert replace(stale, tokenization_key=KEY).tokenization_key_refusal is None


def test_neither_repr_shows_the_key() -> None:
    settings = with_tokenization_key(_settings(), _migrated())
    resolution = resolve_tokenization_key(_settings(), _migrated())
    for text in (repr(settings), str(settings), repr(resolution), str(resolution)):
        assert KEY not in text and KEY[:16] not in text


@pytest.mark.parametrize(
    ("state", "key"),
    [(TokenizationKeyState.LOADED, None), (TokenizationKeyState.ABSENT, KEY)],
    ids=["loaded-without-a-key", "keyless-state-with-a-key"],
)
def test_a_resolution_carries_a_key_exactly_when_loaded(
    state: TokenizationKeyState, key: str | None
) -> None:
    with pytest.raises(ValueError, match="exactly when it is loaded") as refused:
        TokenizationKeyResolution(state=state, origin=TokenizationKeyOrigin.NONE, key=key)
    assert KEY not in str(refused.value)


# --- dev ------------------------------------------------------------------------------


def test_dev_on_the_openbao_dev_server_reads_openbao_like_everywhere() -> None:
    vault = _migrated(origin="generated")
    resolution = resolve_tokenization_key(_settings("dev"), vault)
    assert vault.paths == [TOKENIZATION_KV_PATH]
    assert resolution.origin is TokenizationKeyOrigin.GENERATED


def test_dev_under_file_dev_takes_a_process_local_key_and_reads_no_vault() -> None:
    vault = _migrated()
    first = resolve_tokenization_key(_settings("dev", "file-dev"), vault)
    second = resolve_tokenization_key(_settings("dev", "file-dev"), vault)
    assert vault.paths == []
    assert first.state is TokenizationKeyState.LOADED
    assert first.origin is TokenizationKeyOrigin.PROCESS_LOCAL
    assert first.key is not None and second.key is not None
    assert first.key != second.key, "random per process, never a literal"
    assert first.key != KEY


def test_near_miss_file_dev_outside_dev_still_reads_openbao() -> None:
    """from_env refuses file-dev outside dev (INT-325); constructed directly,
    the escape still belongs to dev alone."""
    vault = _migrated()
    resolution = resolve_tokenization_key(_settings("staging", "file-dev"), vault)
    assert vault.paths == [TOKENIZATION_KV_PATH]
    assert resolution.origin is TokenizationKeyOrigin.ENV_FILE


# --- the tiers that need it: 503 with the typed reason --------------------------------


RECIPIENTS = """
version: 1
recipients:
  - recipient_id: unit-lane-hbys-previsit-read
    tenant_id: {tenant_id}
    dpa_ref: dpa/unit-lane/2026-01
    approval_ref: approval/tier3/unit-lane
    retention_ref: dpa/unit-lane/2026-01#clause-7.2
"""


def _recipients(tmp_path: Path, tenant_id: uuid.UUID) -> Path:
    path = tmp_path / "recipients.yaml"
    path.write_text(RECIPIENTS.format(tenant_id=tenant_id), encoding="utf-8")
    return path


@pytest.fixture(params=["tokenization_key_absent", "tokenization_key_unreadable"])
def keyless(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[tuple[Any, str]]:
    reason: str = request.param
    for harness in build_harness(
        tmp_path,
        token_patient=PATIENT_TOKEN,
        token_admin=ADMIN_TOKEN,
        tokenization_key_refusal=reason,
        previsit_output_recipients=_recipients(tmp_path, DEV_TENANT_ID),
    ):
        yield harness, reason


def test_the_otp_tier_answers_503_with_the_typed_reason(keyless: tuple[Any, str]) -> None:
    harness, reason = keyless
    response = harness.client.post("/v1/auth/otp/request", json={"phone": NUMBER})
    assert response.status_code == 503
    assert response.json() == {"error": "otp_auth_unconfigured", "reason": reason}


def test_the_previsit_read_back_answers_503_with_the_typed_reason(
    keyless: tuple[Any, str],
) -> None:
    harness, reason = keyless
    response = harness.client.post(
        "/v1/previsit-output/fetch", json={"patient_number": "90000042"}, headers=harness.admin()
    )
    assert response.status_code == 503
    assert response.json() == {"error": "previsit_output_unconfigured", "reason": reason}


def test_near_miss_with_a_key_the_otp_503_names_no_key_reason(tmp_path: Path) -> None:
    """A tier down for another reason (no Redis, no vendor) says nothing about
    the key: the reason is the key's, and only when the key is the cause."""
    for harness in build_harness(
        tmp_path, token_patient=PATIENT_TOKEN, token_admin=ADMIN_TOKEN, tokenization_key=KEY
    ):
        response = harness.client.post("/v1/auth/otp/request", json={"phone": NUMBER})
        assert response.status_code == 503
        assert response.json() == {"error": "otp_auth_unconfigured"}
