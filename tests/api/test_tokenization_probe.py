"""INT-584 (owner decision D38) — the before/after pseudonym-equality probe.

``python -m intake_api.tokenization_probe`` runs in a one-off api container on
the synthetic host (``infra/staging/tokenization_key.sh``). ``record`` takes the
env copy of the key on stdin and fingerprints the fixed synthetic number's
pseudonym under it, before anything moves; ``compare`` takes that fingerprint
on stdin, resolves the key exactly as the API does at boot, and prints
``equal`` or ``differ`` — nothing else, ever. Pinned with near misses: a key
one character away, another key id, a vault with nothing in it, a record that
is not a fingerprint. No mode prints the key, the pseudonym or the number.
"""

from __future__ import annotations

import hashlib
import io
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from intake_api.settings import ApiSettings
from intake_api.tokenization_key import TOKENIZATION_KV_PATH
from intake_api.tokenization_probe import (
    CANNOT_COMPARE,
    DIFFER,
    EQUAL,
    PROBE_NUMBER,
    main,
)
from intake_platform.tokenization import Tokenizer

KEY = "3f" * 8 + "a1" * 8 + "0c" * 8 + "e7" * 8
NEAR_KEY = KEY[:-1] + ("0" if KEY[-1] != "0" else "1")


class Vault:
    def __init__(self, document: dict[str, Any] | None = None, status: int | None = None) -> None:
        self.document = document
        self.status = status

    def get_kv(self, path: str) -> dict[str, Any]:
        assert path == TOKENIZATION_KV_PATH
        if self.status is not None or self.document is None:
            request = httpx.Request("GET", "http://openbao:8200/v1/secret/data/api/tokenization")
            response = httpx.Response(self.status or 404)
            raise httpx.HTTPStatusError("refused", request=request, response=response)
        return dict(self.document)


def _settings_factory(key_id: str = "v1") -> Callable[[], ApiSettings]:
    def factory() -> ApiSettings:
        return ApiSettings(
            token_patient=None,
            token_admin=None,
            app_db_url="postgresql+psycopg://app_rw@db.internal:5432/intake",
            audit_db_url="postgresql+psycopg://svc_audit_writer@db.internal:5432/intake",
            bootstrap_db_url="postgresql+psycopg://intake_owner@db.internal:5432/intake",
            kek_mode="transit",
            environment="staging",
            tokenization_key_id=key_id,
        )

    return factory


def _run(
    mode: str, stdin: str, vault: Vault | None = None, key_id: str = "v1"
) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = main(
        [mode],
        stdin=io.StringIO(stdin),
        stdout=out,
        stderr=err,
        settings_factory=_settings_factory(key_id),
        secrets_reader=vault if vault is not None else Vault(),
    )
    return code, out.getvalue(), err.getvalue()


def _record(key: str = KEY) -> str:
    code, out, _ = _run("record", key + "\n")
    assert code == EQUAL, "record succeeds on a well-formed key"
    return out.strip()


def _pseudonym(key: str, key_id: str = "v1") -> str:
    return Tokenizer(keys={key_id: key.encode("utf-8")}, active_key_id=key_id).pseudonym(
        PROBE_NUMBER
    )


def _assert_shows_nothing(*texts: str) -> None:
    for text in texts:
        for secret in (KEY, NEAR_KEY, _pseudonym(KEY), _pseudonym(KEY).split(".", 1)[1][:16]):
            assert secret not in text
        assert PROBE_NUMBER not in text


def test_the_probe_number_is_synthetic() -> None:
    """Not a Turkish mobile, so it can belong to no subscriber; it never leaves
    the process anyway."""
    assert PROBE_NUMBER.startswith("+90") and PROBE_NUMBER[3] != "5"


def test_record_prints_a_one_way_fingerprint_of_the_pseudonym_only() -> None:
    code, out, err = _run("record", KEY + "\n")
    assert code == EQUAL
    fingerprint = out.strip()
    assert out == fingerprint + "\n"
    assert len(fingerprint) == 64 and int(fingerprint, 16) >= 0
    assert fingerprint != hashlib.sha256(_pseudonym(KEY).encode()).hexdigest(), "domain-separated"
    _assert_shows_nothing(out, err)


@pytest.mark.parametrize("stdin", ["", "\n", "ab" * 8, KEY.upper(), "zz" * 32])
def test_record_refuses_anything_but_a_well_formed_key(stdin: str) -> None:
    code, out, err = _run("record", stdin)
    assert code == CANNOT_COMPARE
    assert out == ""
    _assert_shows_nothing(err)


def test_compare_says_equal_when_openbao_holds_the_recorded_key() -> None:
    code, out, err = _run("compare", _record() + "\n", Vault({"key": KEY, "origin": "env_file"}))
    assert (code, out) == (EQUAL, "equal\n")
    _assert_shows_nothing(out, err)


def test_near_miss_a_key_one_character_away_says_differ() -> None:
    code, out, err = _run("compare", _record() + "\n", Vault({"key": NEAR_KEY}))
    assert (code, out) == (DIFFER, "differ\n")
    _assert_shows_nothing(out, err)


def test_near_miss_the_same_key_under_another_key_id_says_differ() -> None:
    """The fingerprint covers the whole pseudonym, key id included."""
    code, out, _ = _run("compare", _record() + "\n", Vault({"key": KEY}), key_id="v2")
    assert (code, out) == (DIFFER, "differ\n")


@pytest.mark.parametrize(
    ("vault", "reason"),
    [
        (Vault(), "tokenization_key_absent"),
        (Vault(status=403), "tokenization_key_unreadable"),
        (Vault({"key": "ab" * 8}), "tokenization_key_malformed"),
    ],
    ids=["absent", "unreadable", "malformed"],
)
def test_no_key_to_compare_says_differ_and_why(vault: Vault, reason: str) -> None:
    code, out, err = _run("compare", _record() + "\n", vault)
    assert (code, out) == (CANNOT_COMPARE, "differ\n")
    assert reason in err
    _assert_shows_nothing(out, err)


@pytest.mark.parametrize("record", ["", "not-a-fingerprint", "ab" * 31, "AB" * 32])
def test_no_before_record_says_differ(record: str) -> None:
    code, out, err = _run("compare", record, Vault({"key": KEY}))
    assert (code, out) == (CANNOT_COMPARE, "differ\n")
    assert "before" in err
    _assert_shows_nothing(out, err)


@pytest.mark.parametrize("argv", [[], ["show"], ["record", "extra"]])
def test_an_unknown_mode_is_refused_and_prints_nothing(argv: list[str]) -> None:
    out, err = io.StringIO(), io.StringIO()
    code = main(
        argv,
        stdin=io.StringIO(KEY),
        stdout=out,
        stderr=err,
        settings_factory=_settings_factory(),
        secrets_reader=Vault({"key": KEY}),
    )
    assert code == CANNOT_COMPARE
    assert out.getvalue() == ""
    _assert_shows_nothing(err.getvalue())
