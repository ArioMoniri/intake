"""INT-488 — four guards the security re-review suggested before the PR (30 Oct 2026).

- **R1** the erasure role is refused at start when it is the bootstrap role, or
  holds ``rolsuper`` or ``rolbypassrls``; the app role passes (near miss);
- **R3** an unrecorded-close entry names one of three fixed actors or is
  recorded as unattributed, and the sweep's three stages are isolated, so a
  poisoned entry or a failing stage never stops the expiry or the erasure retry;
- **R2** a blocked erasure writes its ``reset_blocked`` rows once per episode,
  not once a minute;
- **R6** ``--on`` writes ``opened`` only when the window really opened.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import fakeredis
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

from api_harness import run  # noqa: E402
from intake_api.audit import AuditWriter  # noqa: E402
from intake_api.dsar.grants import Privilege  # noqa: E402
from test_otp_abuse import DpopClient, OtpHarness  # noqa: E402
from test_review_signin import answer, ask, cli, draw, harness, review  # noqa: E402
from test_review_signin_reset import seed_session, sessions_of  # noqa: E402

DAY = 24 * 3600
APP = "postgresql+psycopg://app_rw:pw@db.internal:5432/intake"
OWNER = "postgresql+psycopg://intake:pw@db.internal:5432/intake"
MISSING = (Privilege("patient_overlays", "DELETE"),)


def reset_module() -> Any:
    return __import__("intake_api.review_reset", fromlist=["erasure_role_problem"])


def sweep(otp: OtpHarness) -> None:
    otp.client.portal.call(otp.client.app.state.api.auth.review_sweep)


def rows_of(otp: OtpHarness, action: str) -> list[Any]:
    return [entry for entry in otp.audit_store.entries() if entry.action == action]


def attributes(superuser: bool, bypass: bool) -> Any:
    async def read(engine: Any) -> tuple[bool, bool]:
        del engine
        return superuser, bypass

    return read


ENGINE = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))


# --- R1: the erasure role is checked at start --------------------------------------------------


@pytest.mark.parametrize(
    ("erasure_url", "superuser", "bypass", "named"),
    [
        (OWNER, False, False, "bootstrap"),
        (APP, True, False, "rolsuper"),
        (APP, False, True, "rolbypassrls"),
        (APP, True, True, "rolsuper, rolbypassrls"),
    ],
    ids=["the-bootstrap-role", "superuser", "bypasses-rls", "both"],
)
def test_a_privileged_erasure_role_is_refused(
    erasure_url: str, superuser: bool, bypass: bool, named: str
) -> None:
    problem = run(
        reset_module().erasure_role_problem(
            ENGINE,
            bootstrap_url=OWNER,
            erasure_url=erasure_url,
            attributes=attributes(superuser, bypass),
        )
    )
    assert problem is not None and named in problem and "INT-394" in problem
    assert "pw" not in problem, "no credential in the refusal"


def test_near_miss_the_app_role_passes() -> None:
    problem = run(
        reset_module().erasure_role_problem(
            ENGINE, bootstrap_url=OWNER, erasure_url=APP, attributes=attributes(False, False)
        )
    )
    assert problem is None


def test_a_refused_role_erases_nothing_and_says_why(tmp_path: Path) -> None:
    reviewer = draw()
    module = reset_module()
    with harness(tmp_path, reviewer) as otp:
        bundle = answer(otp, DpopClient(), reviewer, ask(otp, reviewer)).json()
        seed_session(otp, review().REVIEW_TENANT_ID, uuid.UUID(bundle["patient_id"]))
        guard = module.ErasureRoleGuard(
            otp.engine, bootstrap_url=OWNER, erasure_url=APP, attributes=attributes(True, False)
        )
        reset = module.review_reset_for(otp.engine, None, AuditWriter(otp.audit_store), guard=guard)
        with pytest.raises(module.ReviewResetBlocked) as refused:
            run(reset("operator:host"))
        assert "rolsuper" in str(refused.value)
        assert sessions_of(otp, bundle["patient_id"]) != [], "nothing was erased"
        # near miss: the app role erases
        allowed = module.ErasureRoleGuard(
            otp.engine, bootstrap_url=OWNER, erasure_url=APP, attributes=attributes(False, False)
        )
        reset = module.review_reset_for(
            otp.engine, None, AuditWriter(otp.audit_store), guard=allowed
        )
        run(reset("operator:host"))
        assert sessions_of(otp, bundle["patient_id"]) == []


def test_the_owner_command_refuses_the_bootstrap_role_before_connecting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import intake_api.db as db_module

    connected: list[str] = []
    monkeypatch.delenv("INTAKE_ENV", raising=False)
    monkeypatch.setenv("INTAKE_API_DB_URL", APP)
    monkeypatch.setenv("INTAKE_API_BOOTSTRAP_DB_URL", OWNER)
    monkeypatch.setenv("INTAKE_API_AUDIT_DB_URL", f"sqlite+pysqlite:///{tmp_path / 'audit.db'}")
    monkeypatch.setenv("INTAKE_API_ERASURE_DB_URL", OWNER)
    monkeypatch.setattr(db_module, "build_engine", lambda url: connected.append(url))
    cli = __import__("intake_api.review_cli", fromlist=["_default_reset"])
    problem = cli._default_reset()
    assert problem is not None and "bootstrap" in problem and "INT-394" in problem
    assert connected == [], "refused before any engine was built"


def test_a_superuser_erasure_role_is_refused_from_the_apis_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    import logging

    caplog.set_level(logging.WARNING, logger="intake_api")
    monkeypatch.setattr(reset_module(), "pg_role_attributes", attributes(True, False))
    reviewer = draw()
    with harness(tmp_path, reviewer) as otp:
        assert "review erasure role refused at start" in caplog.text
        assert "rolsuper" in caplog.text
        bundle = answer(otp, DpopClient(), reviewer, ask(otp, reviewer)).json()
        seed_session(otp, review().REVIEW_TENANT_ID, uuid.UUID(bundle["patient_id"]))
        otp.clock.advance(14 * DAY)
        sweep(otp)
        # the expiry ran; the erasure refused, typed and audited, and paged
        assert otp.redis_client.get("auth:review:window") is None
        [blocked] = rows_of(otp, "auth.review.reset_blocked")
        assert blocked.resource_ref == "review_signin:erasure_role"
        assert len(rows_of(otp, "auth.review.reset_failed")) == 1
        assert sessions_of(otp, bundle["patient_id"]) != [], "nothing was erased"


def test_a_role_check_that_cannot_answer_refuses() -> None:
    async def down(engine: Any) -> tuple[bool, bool]:
        raise ConnectionError("catalogue unreachable")

    guard = reset_module().ErasureRoleGuard(
        ENGINE, bootstrap_url=OWNER, erasure_url=APP, attributes=down
    )
    problem = run(guard.problem())
    assert problem is not None and "could not be checked (ConnectionError)" in problem


def test_an_unlisted_role_reads_as_privileged() -> None:
    class Result:
        def first(self) -> None:
            return None

    class Conn:
        async def __aenter__(self) -> Conn:
            return self

        async def __aexit__(self, *exc: object) -> None:
            return None

        async def execute(self, statement: Any) -> Result:
            assert "current_user" in str(statement)
            return Result()

    engine = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"), connect=Conn)
    assert run(reset_module().pg_role_attributes(engine)) == (True, True)
    sqlite = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    assert run(reset_module().pg_role_attributes(sqlite)) is None, "no roles off PostgreSQL"


@pytest.mark.parametrize(
    ("erasure_url", "refused"),
    [("postgresql+psycopg://intake_owner@db.internal:5432/intake", True), (None, False)],
    ids=["names-the-bootstrap-role", "near-miss-the-app-role"],
)
def test_the_api_checks_the_role_its_erasure_runs_as(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, erasure_url: str | None, refused: bool
) -> None:
    import intake_api.app as app_module
    from intake_api.app import ApiWiring, create_app
    from intake_api.attestation import DevStructuralAttestationVerifier
    from intake_api.otp import AuthWiring, DevLogDeliveryAdapter
    from intake_platform.audit import InMemoryAuditStore
    from intake_platform.envelope import EnvelopeCipher, FileKekProvider
    from sqlalchemy.ext.asyncio import create_async_engine
    from test_review_signin import TOKENIZER, strict

    guards: list[Any] = []
    real = app_module.review_reset_for

    def spy(engine: Any, documents: Any, audit: Any, **kwargs: Any) -> Any:
        guards.append(kwargs.get("guard"))
        return real(engine, documents, audit, **kwargs)

    monkeypatch.setattr(app_module, "review_reset_for", spy)
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'app.db'}")
    create_app(
        ApiWiring(
            settings=strict(erasure_db_url=erasure_url),
            engine=engine,
            audit_store=InMemoryAuditStore(),
            cipher=EnvelopeCipher(FileKekProvider()),
            bootstrap=False,
            auth=AuthWiring(
                redis_client=fakeredis.FakeStrictRedis(),
                tokenizer=TOKENIZER,
                delivery=DevLogDeliveryAdapter(),
                attestation=DevStructuralAttestationVerifier(),
            ),
        )
    )
    [guard] = guards
    assert isinstance(guard, reset_module().ErasureRoleGuard)
    problem = run(guard.problem())
    assert (problem is not None and "bootstrap" in problem) is refused
    run(engine.dispose())


# --- R3: fixed actors, isolated stages ---------------------------------------------------


@pytest.mark.parametrize(
    "entry",
    [
        '{"actor": "has a space", "at": 1}',
        '{"actor": "patient:someone", "at": 1}',
        "not json at all",
        '{"actor": 7}',
        '{"at": 1}',
    ],
    ids=["not-ref-shaped", "unknown-actor", "garbled", "actor-not-a-string", "no-actor"],
)
def test_a_poisoned_close_entry_still_lets_expiry_and_the_retry_run(
    tmp_path: Path, entry: str
) -> None:
    reviewer = draw()
    with harness(tmp_path, reviewer) as otp:
        window = review().ReviewWindow(otp.redis_client, otp.clock)
        bundle = answer(otp, DpopClient(), reviewer, ask(otp, reviewer)).json()
        seed_session(otp, review().REVIEW_TENANT_ID, uuid.UUID(bundle["patient_id"]))
        otp.redis_client.rpush("auth:review:unrecorded_closes", entry)
        otp.clock.advance(14 * DAY)
        sweep(otp)
        # the expiry ran, and the erasure after it
        assert otp.redis_client.get("auth:review:window") is None
        assert [row.actor for row in rows_of(otp, "auth.review.window.closed")].count(
            "system:review-expiry"
        ) == 1
        assert sessions_of(otp, bundle["patient_id"]) == []
        # the poisoned entry is recorded as unattributed, never under its own words
        assert window.unrecorded_closes() == 0
        unattributed = rows_of(otp, "auth.review.window.closed_unattributed")
        assert [row.actor for row in unattributed] == ["system:review-guard"]
        chain = repr(list(otp.audit_store.entries()))
        assert not any(word in chain for word in ("patient:someone", "not json", "a space"))


def test_near_miss_each_fixed_actor_is_kept() -> None:
    fake = fakeredis.FakeStrictRedis()
    window = review().ReviewWindow(fake)
    for actor in ("operator:host", "system:review-expiry", "system:review-guard"):
        window.note_unrecorded_close(actor)
        assert window.first_unrecorded_close() == actor
        window.recorded_close()


def test_an_unknown_actor_is_never_queued() -> None:
    window = review().ReviewWindow(fakeredis.FakeStrictRedis())
    with pytest.raises(ValueError):
        window.note_unrecorded_close("patient:someone")
    assert window.unrecorded_closes() == 0


def test_a_failing_stage_never_stops_the_others(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from intake_api.review_flow import ReviewSignInFlow

    async def boom(self: Any) -> None:
        raise RuntimeError("stage down")

    reviewer = draw()
    with harness(tmp_path, reviewer) as otp:
        bundle = answer(otp, DpopClient(), reviewer, ask(otp, reviewer)).json()
        seed_session(otp, review().REVIEW_TENANT_ID, uuid.UUID(bundle["patient_id"]))
        otp.clock.advance(14 * DAY)
        monkeypatch.setattr(ReviewSignInFlow, "_record_closes", boom)
        sweep(otp)  # does not raise
        assert otp.redis_client.get("auth:review:window") is None, "the expiry ran"
        assert sessions_of(otp, bundle["patient_id"]) == [], "the erasure ran"


# --- R2: one reset_blocked row per episode -----------------------------------------------


def test_a_blocked_erasure_is_on_the_chain_once_per_episode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = reset_module()
    real = module.reset_review_tenant

    async def missing(session: Any) -> tuple[Privilege, ...]:
        del session
        return MISSING

    async def blocked(*args: Any, **kwargs: Any) -> int:
        return int(await real(*args, **{**kwargs, "privileges": missing}))

    reviewer = draw()
    with harness(tmp_path, reviewer) as otp:
        bundle = answer(otp, DpopClient(), reviewer, ask(otp, reviewer)).json()
        seed_session(otp, review().REVIEW_TENANT_ID, uuid.UUID(bundle["patient_id"]))
        assert cli("off", otp.redis_client, reset=lambda: "blocked", now_fn=otp.clock)[0] == 1
        monkeypatch.setattr(module, "reset_review_tenant", blocked)
        for _ in range(3):
            sweep(otp)
        assert len(rows_of(otp, "auth.review.reset_blocked")) == len(MISSING)
        assert len(rows_of(otp, "auth.review.reset_failed")) == 1
        # near miss: the owner's own command records its refusal every time
        before = len(rows_of(otp, "auth.review.reset_blocked"))
        with pytest.raises(module.ReviewResetBlocked):
            run(
                real(
                    otp.engine,
                    audit=AuditWriter(otp.audit_store),
                    remove_object=lambda ref: None,
                    now=__import__("datetime").datetime.now(__import__("datetime").UTC),
                    privileges=missing,
                )
            )
        assert len(rows_of(otp, "auth.review.reset_blocked")) == before + len(MISSING)


# --- R6: "opened" only for a window that opened --------------------------------------------


class RaceLost(fakeredis.FakeStrictRedis):
    """Another opening lands between the read and the SET NX."""

    def set(self, *args: Any, **kwargs: Any) -> Any:
        if kwargs.get("nx"):
            return None
        return super().set(*args, **kwargs)


class SetFails(fakeredis.FakeStrictRedis):
    def set(self, *args: Any, **kwargs: Any) -> Any:
        import redis

        raise redis.ConnectionError("down")


@pytest.mark.parametrize("store", [RaceLost, SetFails], ids=["race-lost", "store-down"])
def test_on_writes_opened_only_for_a_window_that_opened(store: Any) -> None:
    code, said, audited = cli("on", store())
    assert code == 1
    assert "auth.review.window.opened" not in audited


def test_an_opening_whose_row_fails_is_closed_again() -> None:
    fake = fakeredis.FakeStrictRedis()

    def down(action: str) -> None:
        raise RuntimeError("audit store down")

    code, said, _ = cli("on", fake, audit=down)
    assert code == 1
    assert review().ReviewWindow(fake).is_open() is False, "an unrecorded opening does not stay"
    assert review().ReviewWindow(fake).unrecorded_closes() == 1, "its close is recorded later"


def test_near_miss_an_opening_that_opened_is_recorded() -> None:
    fake = fakeredis.FakeStrictRedis()
    code, _, audited = cli("on", fake)
    assert code == 0 and audited == ["auth.review.window.opened"]
    assert review().ReviewWindow(fake).is_open()
