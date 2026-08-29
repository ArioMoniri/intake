"""INT-013 — tokenization service + identity vault (KVKK-6/12, 2018/10).

Acceptance, verbatim:
  "HMAC-SHA-256 keyed pseudonym for joins; encrypted value in identity_vault
   readable only by the tokenization role; logs get pseudonym[:8]"
  "roundtrip + key-rotation tests; grep-test proves no app table stores raw
   TCKN/phone"
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from intake_platform.tokenization import (
    DIGEST_HEX_LEN,
    KEY_ID_SHAPE,
    MAX_KEY_ID_LEN,
    PSEUDONYM_MAX_LEN,
    InvalidKeyIdError,
    Tokenizer,
)

REPO = Path(__file__).resolve().parents[2]

KEYS_V1 = {"v1": b"unit-test-key-one"}
KEYS_V2 = {"v1": b"unit-test-key-one", "v2": b"unit-test-key-two"}


# --- pseudonyms (unit) ------------------------------------------------------------


def test_pseudonym_is_deterministic_and_keyed() -> None:
    tok = Tokenizer(keys=KEYS_V1, active_key_id="v1")
    p1 = tok.pseudonym("12345678901")
    assert p1 == tok.pseudonym("12345678901"), "joins need determinism"
    assert p1.startswith("v1."), "pseudonyms carry their key id"
    other = Tokenizer(keys={"v1": b"a-different-key"}, active_key_id="v1")
    assert other.pseudonym("12345678901") != p1, "pseudonyms must be keyed, not plain hashes"


def test_pseudonym_normalises_identifier_formatting() -> None:
    tok = Tokenizer(keys=KEYS_V1, active_key_id="v1")
    assert tok.pseudonym("0532 111 44 55") == tok.pseudonym("05321114455")
    assert tok.pseudonym(" 12345678901 ") == tok.pseudonym("12345678901")


def test_raw_value_is_not_recoverable_from_pseudonym() -> None:
    tok = Tokenizer(keys=KEYS_V1, active_key_id="v1")
    p = tok.pseudonym("12345678901")
    assert "12345678901" not in p


def test_log_ref_is_the_short_prefix_and_never_the_raw() -> None:
    tok = Tokenizer(keys=KEYS_V1, active_key_id="v1")
    ref = tok.log_ref("05321114455")
    digest = tok.pseudonym("05321114455").split(".", 1)[1]
    assert ref == digest[:8], "logs get pseudonym[:8]"
    assert "0532" not in ref


# --- key rotation (unit) ----------------------------------------------------------


def test_rotation_moves_new_writes_and_keeps_old_verifiable() -> None:
    old = Tokenizer(keys=KEYS_V1, active_key_id="v1")
    p_old = old.pseudonym("12345678901")

    rotated = Tokenizer(keys=KEYS_V2, active_key_id="v2")
    p_new = rotated.pseudonym("12345678901")
    assert p_new.startswith("v2.")
    assert p_new != p_old

    # an old pseudonym is still linkable: the same value re-tokenised under the
    # old key id must reproduce it (re-tokenisation jobs depend on this)
    assert rotated.pseudonym("12345678901", key_id="v1") == p_old


def test_unknown_key_id_is_refused() -> None:
    tok = Tokenizer(keys=KEYS_V1, active_key_id="v1")
    with pytest.raises(KeyError):
        tok.pseudonym("12345678901", key_id="v9")


# --- INT-228: the pseudonym's shape is a contract, not an observation -------------


@pytest.mark.parametrize(
    "bad_key_id",
    ["", "has/slash", "has space", "-leading", "anahtarı", "v" * (MAX_KEY_ID_LEN + 1)],
)
def test_a_misshapen_key_id_is_refused_at_construction(bad_key_id: str) -> None:
    """A key id rides inside every pseudonym derived under it, so an unbounded
    one makes PSEUDONYM_MAX_LEN a lie and every downstream module that sized
    itself against it wrong. Refused where the key set is assembled, not where
    the pseudonym is used — the value is not echoed (invariant 6)."""
    with pytest.raises(InvalidKeyIdError) as excinfo:
        Tokenizer(keys={bad_key_id: b"unit-test-key"}, active_key_id=bad_key_id)
    if bad_key_id:
        assert bad_key_id not in str(excinfo.value)


@settings(max_examples=50, deadline=None)
@given(
    key_id=st.from_regex(KEY_ID_SHAPE, fullmatch=True),
    # synthetic identifiers only — digits and the punctuation _normalise strips
    identifier=st.text(alphabet="0123456789 +-().", min_size=1, max_size=32),
)
def test_every_pseudonym_is_inside_the_published_bound(key_id: str, identifier: str) -> None:
    """What downstream code is entitled to assume: whatever key id is
    configured and whatever identifier arrives, the pseudonym is
    ``<key_id>.<64 hex>`` and no longer than PSEUDONYM_MAX_LEN. The document
    store sizes its object keys against exactly this."""
    pseudonym = Tokenizer(keys={key_id: b"unit-test-key"}, active_key_id=key_id).pseudonym(
        identifier
    )
    assert len(pseudonym) <= PSEUDONYM_MAX_LEN
    assert re.fullmatch(rf"[A-Za-z0-9][A-Za-z0-9._-]*\.[0-9a-f]{{{DIGEST_HEX_LEN}}}", pseudonym)


def test_the_bound_is_reachable_so_it_is_not_slack() -> None:
    tok = Tokenizer(
        keys={"v" * MAX_KEY_ID_LEN: b"unit-test-key"}, active_key_id="v" * MAX_KEY_ID_LEN
    )
    assert len(tok.pseudonym("12345678901")) == PSEUDONYM_MAX_LEN


# --- the grep gate: no app table stores raw TCKN/phone ----------------------------


def test_no_app_table_defines_raw_identifier_columns() -> None:
    """Scan every committed SQL/schema artefact: a column named after a raw
    identifier (tckn/phone/msisdn) may exist ONLY inside the identity vault
    DDL, and there only as ciphertext + pseudonym. This binds every future
    migration the moment it lands (INT-030 inherits the gate)."""
    pattern = re.compile(
        r"\b(tckn|phone|msisdn|telefon)\w*\s+(text|varchar|char|bytea|integer|bigint)", re.I
    )
    offenders: list[str] = []
    for sql in REPO.rglob("*.sql"):
        if ".venv" in sql.parts or "node_modules" in sql.parts:
            continue
        for n, line in enumerate(sql.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line):
                if sql.name == "identity_vault.sql" and "ciphertext" in line:
                    continue
                offenders.append(f"{sql.relative_to(REPO)}:{n}: {line.strip()}")
    assert not offenders, "raw identifier column outside the vault:\n" + "\n".join(offenders)


def test_vault_ddl_stores_only_pseudonym_and_ciphertext() -> None:
    ddl = (REPO / "scripts" / "security" / "identity_vault.sql").read_text(encoding="utf-8")
    assert "pseudonym" in ddl and "ciphertext" in ddl
    assert not re.search(r"\braw_\w+\b", ddl), "the vault never stores a raw column"
    assert "REVOKE" in ddl and "tokenization_role" in ddl, (
        "the vault must be readable only by the tokenization role"
    )


# --- integration: vault roundtrip against Postgres + OpenBao Transit --------------


@pytest.mark.integration
def test_vault_roundtrip_and_role_isolation() -> None:
    import psycopg
    from intake_platform.secrets import SecretsProvider
    from intake_platform.tokenization import IdentityVault

    provider = SecretsProvider.from_env()
    tok = Tokenizer(keys={"v1": b"integration-hmac-key"}, active_key_id="v1")
    tokenization_dsn = (
        "host=127.0.0.1 port=5432 dbname=intake "
        "user=tokenization_role password=tokenization-dev-only"
    )
    vault = IdentityVault(secrets=provider, dsn=tokenization_dsn)

    raw = "12345678901"
    pseudonym = tok.pseudonym(raw)
    vault.store(pseudonym=pseudonym, key_id="v1", raw_value=raw)

    # roundtrip through Transit decrypt, via the tokenization role
    assert vault.fetch(pseudonym) == raw

    # the ciphertext at rest is not the raw value
    with (
        psycopg.connect(tokenization_dsn) as conn,
        conn.cursor() as cur,
    ):
        cur.execute("SELECT ciphertext FROM identity_vault WHERE pseudonym = %s", (pseudonym,))
        row = cur.fetchone()
        assert row is not None and raw not in str(row[0])

    # the app role cannot read the vault at all
    with (
        psycopg.connect(
            "host=127.0.0.1 port=5432 dbname=intake user=app_role password=app-dev-only"
        ) as conn,
        conn.cursor() as cur,
    ):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute("SELECT * FROM identity_vault LIMIT 1")
