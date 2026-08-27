-- INT-013 — the identity vault: the only place a raw identifier exists, and
-- only as OpenBao Transit ciphertext. Readable by tokenization_role alone;
-- the app role cannot SELECT it (proven by the integration test). Dev-tier
-- bootstrap; INT-030's Alembic migrations inherit this shape (and the grep
-- gate in tests/security/test_tokenization_roundtrip.py binds them).

CREATE TABLE IF NOT EXISTS identity_vault (
    pseudonym  text PRIMARY KEY,
    key_id     text NOT NULL,
    ciphertext text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'tokenization_role') THEN
        CREATE ROLE tokenization_role LOGIN PASSWORD 'tokenization-dev-only';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_role') THEN
        CREATE ROLE app_role LOGIN PASSWORD 'app-dev-only';
    END IF;
END
$$;

REVOKE ALL ON identity_vault FROM PUBLIC;
REVOKE ALL ON identity_vault FROM app_role;
GRANT SELECT, INSERT ON identity_vault TO tokenization_role;
GRANT CONNECT ON DATABASE intake TO tokenization_role;
GRANT CONNECT ON DATABASE intake TO app_role;
