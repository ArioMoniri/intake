"""INT-488 — the second review round (security and legal lanes, 30 Oct 2026).

Each blocker and note, pinned with a near miss:

- **security B1** — the erasure runs as the app role (or the role INT-394
  decides, ``INTAKE_API_ERASURE_DB_URL``), never the owner role. INT-395's
  preflight refuses a role without the grants, typed and audited, even over an
  empty tenant, and ``--on`` then refuses naming INT-394;
- **legal B1** — the reviewer's notice, every element of it, verbatim;
- **legal B2** — one hash-bound notes file, covered by the strict claims scan;
- **legal B3** — the processing record: ``--on`` refuses while any field is
  null or the notice hash differs, naming INT-528 and HB-L11;
- **legal B4 / security N2** — a failed unattended erasure is on the chain,
  pages and is retried; a close whose row was lost is re-recorded;
- **N3** an unreadable OpenBao warns and sets a gauge; **N4** a non-finite or
  future opening reads closed.
"""

from __future__ import annotations

import hashlib
import json
import logging
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

import fakeredis
import httpx
import pytest
import yaml
from prometheus_client import REGISTRY

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

import netgsm_testkit as kit  # noqa: E402
from api_harness import run  # noqa: E402
from intake_api.audit import AuditWriter  # noqa: E402
from intake_api.auth_store import REFRESH_TTL_S, RESEND_COOLDOWN_S  # noqa: E402
from intake_api.dsar.grants import Privilege  # noqa: E402
from intake_api.settings import ApiSettings  # noqa: E402
from test_otp_abuse import DpopClient, OtpHarness  # noqa: E402
from test_review_signin import (  # noqa: E402
    REPO,
    TOKENIZER,
    answer,
    ask,
    cli,
    draw,
    guards,
    harness,
    keyed,
    review,
    strict,
    window_module,
)
from test_review_signin_reset import reset_now, seed_session, sessions_of  # noqa: E402

LEGAL = REPO / "docs" / "legal" / "store" / "review"
NOTES = LEGAL / "app-review-signin-notes.en.md"
RECORD = LEGAL / "review-signin.yaml"
RULES = REPO / "infra" / "observability" / "security-rules.yaml"
MISSING = (Privilege("patient_overlays", "DELETE"),)


def record_module() -> Any:
    return __import__("intake_api.review_record", fromlist=["review_record_problem"])


def reset_module() -> Any:
    return __import__("intake_api.review_reset", fromlist=["reset_review_tenant"])


async def _missing(session: Any) -> tuple[Privilege, ...]:
    del session
    return MISSING


def sweep(otp: OtpHarness) -> None:
    otp.client.portal.call(otp.client.app.state.api.auth.review_sweep)


def rows_of(otp: OtpHarness, action: str) -> list[Any]:
    return [entry for entry in otp.audit_store.entries() if entry.action == action]


def failures() -> float:
    return REGISTRY.get_sample_value("review_reset_failures_total") or 0.0


# --- security B1: the app role, INT-395's preflight, INT-394 named ---------------------------


def test_a_role_without_the_grants_refuses_even_an_empty_tenant(tmp_path: Path) -> None:
    reviewer = draw()
    with harness(tmp_path, reviewer) as otp:
        module = reset_module()
        with pytest.raises(module.ReviewResetBlocked) as refused:
            run(
                module.reset_review_tenant(
                    otp.engine,
                    audit=AuditWriter(otp.audit_store),
                    remove_object=lambda ref: None,
                    now=__import__("datetime").datetime.now(__import__("datetime").UTC),
                    privileges=_missing,
                )
            )
        assert "INT-394" in str(refused.value) and "patient_overlays" in str(refused.value)
        blocked = rows_of(otp, "auth.review.reset_blocked")
        assert [entry.resource_ref for entry in blocked] == [MISSING[0].ref]
        # typed and audited before anything is touched: no erasure filed
        assert rows_of(otp, "auth.review.reset") == []


def test_on_refuses_naming_int394_while_the_erasure_role_lacks_grants(tmp_path: Path) -> None:
    reviewer = draw()
    with harness(tmp_path, reviewer) as otp:
        review().ReviewWindow(otp.redis_client, otp.clock).close()
        code, said, audited = cli(
            "on", otp.redis_client, reset=reset_now(otp, privileges=_missing), now_fn=otp.clock
        )
        assert code == 1 and "INT-394" in said
        assert audited == [], "no opening row: the window never opened"
        assert review().ReviewWindow(otp.redis_client, otp.clock).is_open() is False
        # near miss: a role holding every grant opens the same window
        assert cli("on", otp.redis_client, reset=reset_now(otp), now_fn=otp.clock)[0] == 0


def test_the_api_erases_as_the_app_role_not_the_owner_role(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import intake_api.app as app_module

    engines: list[Any] = []
    real = app_module.review_reset_for

    def spy(engine: Any, documents: Any, audit: Any, **kwargs: Any) -> Any:
        engines.append(engine)
        return real(engine, documents, audit, **kwargs)

    monkeypatch.setattr(app_module, "review_reset_for", spy)
    with harness(tmp_path, draw()) as otp:
        assert engines == [otp.engine], "the app engine, unless INT-394 names a role"

    # with an owner engine wired beside it, the erasure still takes the app
    # engine; with the INT-394 role wired, that role
    from intake_api.app import ApiWiring, create_app
    from intake_api.attestation import DevStructuralAttestationVerifier
    from intake_api.otp import AuthWiring, DevLogDeliveryAdapter
    from intake_platform.audit import InMemoryAuditStore
    from intake_platform.envelope import EnvelopeCipher, FileKekProvider
    from sqlalchemy.ext.asyncio import create_async_engine

    app_engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'app.db'}")
    owner = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'owner.db'}")
    decided = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'erasure.db'}")
    auth = AuthWiring(
        redis_client=fakeredis.FakeStrictRedis(),
        tokenizer=TOKENIZER,
        delivery=DevLogDeliveryAdapter(),
        attestation=DevStructuralAttestationVerifier(),
    )
    for erasure, expected in ((None, app_engine), (decided, decided)):
        engines.clear()
        create_app(
            ApiWiring(
                settings=strict(),
                engine=app_engine,
                audit_store=InMemoryAuditStore(),
                cipher=EnvelopeCipher(FileKekProvider()),
                bootstrap=False,
                bootstrap_engine=owner,
                erasure_engine=erasure,
                auth=auth,
            )
        )
        assert engines == [expected]
        assert owner not in engines, "never the owner role"
    for engine in (app_engine, owner, decided):
        run(engine.dispose())


@pytest.mark.parametrize("named", [True, False], ids=["int394-role-named", "unset"])
def test_the_erasure_role_seam(monkeypatch: pytest.MonkeyPatch, named: bool) -> None:
    monkeypatch.delenv("INTAKE_ENV", raising=False)
    decided = "postgresql+psycopg://erasure_rw@db.internal:5432/intake"
    if named:
        monkeypatch.setenv("INTAKE_API_ERASURE_DB_URL", decided)
    else:
        monkeypatch.delenv("INTAKE_API_ERASURE_DB_URL", raising=False)
    assert ApiSettings.from_env().erasure_db_url == (decided if named else None)


def test_the_owner_command_erases_as_the_app_role_or_the_decided_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import intake_api.app as app_module
    import intake_api.db as db_module

    urls: list[str] = []

    class Engine:
        async def dispose(self) -> None:
            return None

    def build(url: str) -> Engine:
        urls.append(url)
        return Engine()

    async def reset(engine: Any, **kwargs: Any) -> int:
        return 0

    class Docs:
        client = object()
        bucket_docs = "intake-docs"
        bucket_audit = "intake-audit-worm"

    monkeypatch.delenv("INTAKE_ENV", raising=False)
    monkeypatch.setenv("INTAKE_API_DB_URL", "sqlite+aiosqlite:///app.db")
    monkeypatch.setenv("INTAKE_API_BOOTSTRAP_DB_URL", "sqlite+aiosqlite:///owner.db")
    monkeypatch.setenv("INTAKE_API_AUDIT_DB_URL", f"sqlite+pysqlite:///{tmp_path / 'audit.db'}")
    monkeypatch.setattr(db_module, "build_engine", build)
    monkeypatch.setattr(reset_module(), "reset_review_tenant", reset)
    monkeypatch.setattr(app_module, "_documents_from_env", Docs)
    cli_module = __import__("intake_api.review_cli", fromlist=["_default_reset"])
    assert cli_module._default_reset() is None
    monkeypatch.setenv("INTAKE_API_ERASURE_DB_URL", "sqlite+aiosqlite:///erasure.db")
    assert cli_module._default_reset() is None
    assert urls == ["sqlite+aiosqlite:///app.db", "sqlite+aiosqlite:///erasure.db"]
    assert "sqlite+aiosqlite:///owner.db" not in urls, "never the owner role"


# --- legal B1: the reviewer's notice, verbatim, element by element ---------------------------

#: The reviewer's text (legal lane, 30 Oct 2026), split into its elements.
NOTICE_ELEMENTS = {
    "controller": "Privacy: the developer named in this App Store listing is the data controller"
    " under Türkiye's Law No. 6698 (KVKK).",
    "categories": "While you review, we process your device's IP address, the App Attest and"
    " sign-in keys your device creates, and records of each sign-in and action that hold only"
    " random identifiers and times.",
    "purposes-and-bases": "We do this to let you sign in to this demo account and to keep it"
    " secure (KVKK Art. 5(2)(f); security records also Art. 5(2)(ç)).",
    "no-own-number-no-third-party": "We never ask for your own phone number, and nothing you"
    " enter goes to a third-party AI or messaging service.",
    "processor-and-country": "The server is run for us by Amazon Web Services in the United"
    " States.",
    "erasure": "What you enter is erased when this review window closes, at the latest 14 days"
    " after it opened.",
    "keys-and-records": "Device and session keys expire within 30 days of last use, and the"
    " id-only records are kept as security records.",
    "health-information": "If you enter health information about yourself anyway, it is erased"
    " with everything else.",
    "rights": "You can exercise your KVKK Art. 11 rights through the support contact in this"
    " listing.",
}


@pytest.mark.parametrize("element", sorted(NOTICE_ELEMENTS))
def test_every_element_of_the_reviewer_notice_is_in_the_notes(element: str) -> None:
    assert NOTICE_ELEMENTS[element] in NOTES.read_text(encoding="utf-8")


def test_the_notice_is_one_paragraph_in_the_reviewers_order() -> None:
    paragraph = " ".join(NOTICE_ELEMENTS[key] for key in NOTICE_ELEMENTS)
    assert paragraph + "\n" in NOTES.read_text(encoding="utf-8")


def test_the_notice_says_what_the_code_does() -> None:
    """Two of its facts are constants here: if either moves, the notice is wrong."""
    assert window_module().REVIEW_WINDOW_S == 14 * 24 * 3600
    assert REFRESH_TTL_S == 30 * 24 * 3600


# --- legal B2: one hash-bound file, covered by the strict claims scan --------------------------


def test_the_strict_claims_scan_covers_the_notes(tmp_path: Path) -> None:
    script = REPO / "scripts" / "ci" / "claims_scan.sh"
    clean = subprocess.run(  # noqa: S603 — fixed argv, our own gate
        ["bash", str(script), "--strict", str(NOTES)],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO,
    )
    assert clean.returncode == 0, clean.stdout + clean.stderr
    # the tree the gate scans with no arguments holds the file
    assert NOTES.relative_to(REPO).as_posix().startswith("docs/legal/")
    # near miss: the same notes with a performance claim fail the same gate
    claimed = tmp_path / "notes.md"
    claimed.write_text(NOTES.read_text(encoding="utf-8") + "Sign-in accuracy is 99.5%.\n")
    dirty = subprocess.run(  # noqa: S603
        ["bash", str(script), "--strict", str(claimed)],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO,
    )
    assert dirty.returncode == 1


# --- legal B3: the processing record -----------------------------------------------------------


def complete_record(tmp_path: Path, **overrides: object) -> Path:
    document: dict[str, object] = yaml.safe_load(RECORD.read_text(encoding="utf-8"))
    document.update(
        transfer_route="a route counsel names (unit fixture)",
        reviewed_by="a named lawyer (unit fixture)",
        reviewed_on="2026-10-30",
    )
    document.update(overrides)
    path = tmp_path / "review-signin.yaml"
    path.write_text(yaml.safe_dump(document, allow_unicode=True), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "field",
    [
        "purpose",
        "basis",
        "retention",
        "recipients",
        "transfer_route",
        "notice_sha256",
        "reviewed_by",
        "reviewed_on",
    ],
)
def test_each_null_record_field_refuses(tmp_path: Path, field: str) -> None:
    problem = record_module().review_record_problem(
        complete_record(tmp_path, **{field: None}), NOTES
    )
    assert problem is not None and field in problem
    assert "INT-528" in problem and "HB-L11" in problem


def test_near_miss_a_complete_record_bound_to_the_notice_admits(tmp_path: Path) -> None:
    assert record_module().review_record_problem(complete_record(tmp_path), NOTES) is None


def test_a_notice_the_record_does_not_pin_refuses(tmp_path: Path) -> None:
    changed = tmp_path / "notes.md"
    changed.write_text(NOTES.read_text(encoding="utf-8") + "One more line.\n", encoding="utf-8")
    problem = record_module().review_record_problem(complete_record(tmp_path), changed)
    assert problem is not None and "notice_sha256" in problem


def test_the_committed_record_is_the_reviewers_and_refuses_on_today() -> None:
    document = yaml.safe_load(RECORD.read_text(encoding="utf-8"))
    assert set(document) == set(record_module().RECORD_FIELDS)
    assert document["purpose"] == "store review demonstration and security of the review account"
    assert any("m.5/2(f)" in basis for basis in document["basis"])
    assert any("m.5/2(ç)" in basis for basis in document["basis"])
    assert document["notice_sha256"] == hashlib.sha256(NOTES.read_bytes()).hexdigest()
    assert document["transfer_route"] is None, "counsel's (INT-528, HB-L11)"
    problem = record_module().review_record_problem(RECORD, NOTES)
    assert problem is not None and "transfer_route" in problem


def test_readiness_refuses_on_the_committed_record() -> None:
    reviewer = draw()
    vault = kit.Vault({"api/review_signin": {"number": reviewer.number, "code": reviewer.code}})
    problem = review().review_readiness(strict(), vault, guards())
    assert problem is not None and "INT-528" in problem and "HB-L11" in problem


# --- legal B4 and security N2: a failed erasure pages and is retried; a lost row returns ------


def _reviewer_left_data(otp: OtpHarness, reviewer: Any) -> str:
    bundle = answer(otp, DpopClient(), reviewer, ask(otp, reviewer)).json()
    patient: str = bundle["patient_id"]
    seed_session(otp, review().REVIEW_TENANT_ID, uuid.UUID(patient))
    # closed by the owner, whose own erasure failed: the subject is pending
    assert cli("off", otp.redis_client, reset=lambda: "blocked", now_fn=otp.clock)[0] == 1
    return patient


def test_a_failed_unattended_erasure_is_recorded_pages_and_is_retried(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reviewer = draw()
    module = reset_module()
    real = module.reset_review_tenant
    with harness(tmp_path, reviewer) as otp:
        patient = _reviewer_left_data(otp, reviewer)

        async def refused(*args: Any, **kwargs: Any) -> int:
            raise module.ReviewResetBlocked("its role lacks patient_overlays (INT-394)")

        monkeypatch.setattr(module, "reset_review_tenant", refused)
        before = failures()
        sweep(otp)
        [failed] = rows_of(otp, "auth.review.reset_failed")
        assert failed.actor == "system:review-expiry"
        assert failures() == before + 1, "the paging series counts it"
        sweep(otp)
        assert failures() == before + 2, "retried on the next sweep"
        assert len(rows_of(otp, "auth.review.reset_failed")) == 1, "one row per episode"
        assert sessions_of(otp, patient) != []
        # the cause is fixed: the next sweep erases, and writes no failure row
        monkeypatch.setattr(module, "reset_review_tenant", real)
        sweep(otp)
        assert sessions_of(otp, patient) == []
        assert len(rows_of(otp, "auth.review.reset_failed")) == 1
        assert failures() == before + 2


def test_near_miss_a_sweep_that_erases_writes_no_failure_row(tmp_path: Path) -> None:
    reviewer = draw()
    with harness(tmp_path, reviewer) as otp:
        patient = _reviewer_left_data(otp, reviewer)
        before = failures()
        sweep(otp)
        assert sessions_of(otp, patient) == []
        assert rows_of(otp, "auth.review.reset_failed") == []
        assert failures() == before
        assert [entry.actor for entry in rows_of(otp, "auth.review.reset")] == [
            "system:review-expiry"
        ]


def test_the_sweep_never_erases_under_an_open_window(tmp_path: Path) -> None:
    reviewer = draw()
    with harness(tmp_path, reviewer) as otp:
        patient = _reviewer_left_data(otp, reviewer)
        review().ReviewWindow(otp.redis_client, otp.clock).open()
        sweep(otp)
        assert sessions_of(otp, patient) != []


def test_the_reset_failure_alert_pages_and_links_its_runbook() -> None:
    from intake_platform.alert_rules import runbook_problem

    groups = yaml.safe_load(RULES.read_text(encoding="utf-8"))["groups"]
    [rule] = [r for g in groups for r in g["rules"] if r.get("alert") == "ReviewResetFailing"]
    assert "review_reset_failures_total" in rule["expr"]
    assert rule["labels"]["severity"] == "page"
    assert runbook_problem(rule["annotations"]["runbook"], REPO) is None


def test_a_close_whose_row_was_lost_is_re_recorded_by_the_sweep(tmp_path: Path) -> None:
    reviewer = draw()
    with harness(tmp_path, reviewer) as otp:

        def down(action: str) -> None:
            raise RuntimeError("audit store down")

        code, said, _ = cli("off", otp.redis_client, audit=down, now_fn=otp.clock)
        assert code == 1 and "could not be audited" in said
        window = review().ReviewWindow(otp.redis_client, otp.clock)
        assert window.unrecorded_closes() == 1
        assert rows_of(otp, "auth.review.window.closed") == []
        sweep(otp)
        [closed] = rows_of(otp, "auth.review.window.closed")
        assert closed.actor == "operator:host"
        assert window.unrecorded_closes() == 0


def test_an_expiry_whose_row_was_lost_is_re_recorded_under_its_actor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reviewer = draw()
    with harness(tmp_path, reviewer) as otp:
        window = review().ReviewWindow(otp.redis_client, otp.clock)
        window.close()
        window.open()
        otp.clock.advance(14 * 24 * 3600)
        real = otp.audit_store.append
        lost = {"once": True}

        def flaky(entry: Any) -> None:
            if lost.pop("once", False):
                raise RuntimeError("audit store down")
            real(entry)

        monkeypatch.setattr(otp.audit_store, "append", flaky)
        sweep(otp)  # the lost row no longer stops the sweep (security review R3)
        assert otp.redis_client.get("auth:review:window") is None, "closed first"
        assert window.unrecorded_closes() == 1
        sweep(otp)
        [closed] = rows_of(otp, "auth.review.window.closed")
        assert closed.actor == "system:review-expiry"
        assert window.unrecorded_closes() == 0


# --- N3: an OpenBao that cannot answer is not "no reviewer" ------------------------------------


def unreadable() -> float:
    return REGISTRY.get_sample_value("review_signin_document_unreadable") or 0.0


def test_an_unreadable_openbao_warns_and_sets_the_gauge(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="intake_api.review_signin")
    vault = kit.Vault(error=httpx.ConnectError("unreachable"))
    signin = review().review_signin_from_vault(
        vault, settings=strict(), tokenizer=TOKENIZER, pepper=keyed(), guards=guards()
    )
    assert signin is None
    assert unreadable() == 1
    assert any(
        r.levelno == logging.WARNING and "could not be read" in r.getMessage()
        for r in caplog.records
    )


def test_near_miss_an_absent_document_is_info_and_clears_the_gauge(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="intake_api.review_signin")
    signin = review().review_signin_from_vault(
        kit.Vault(), settings=strict(), tokenizer=TOKENIZER, pepper=keyed(), guards=guards()
    )
    assert signin is None
    assert unreadable() == 0
    assert not any(r.levelno >= logging.WARNING for r in caplog.records)


# --- N4: a non-finite or future opening reads closed --------------------------------------------

WINDOW_ID = hashlib.sha256(b"int488-round2-window").hexdigest()[:32]


@pytest.mark.parametrize(
    "since",
    [float("nan"), float("inf"), float("-inf"), 1_000_000.0 + 3600],
    ids=["nan", "inf", "minus-inf", "an-hour-ahead"],
)
def test_a_non_finite_or_future_opening_reads_closed(since: float) -> None:
    fake = fakeredis.FakeStrictRedis()
    fake.set("auth:review:window", json.dumps({"state": "open", "since": since, "id": WINDOW_ID}))
    assert review().ReviewWindow(fake, lambda: 1_000_000.0).is_open() is False


def test_near_miss_an_opening_within_the_clock_skew_reads_open() -> None:
    fake = fakeredis.FakeStrictRedis()
    since = 1_000_000.0 + 30
    fake.set("auth:review:window", json.dumps({"state": "open", "since": since, "id": WINDOW_ID}))
    assert review().ReviewWindow(fake, lambda: 1_000_000.0).is_open() is True


def test_the_reviewer_still_signs_in_on_a_well_formed_window(tmp_path: Path) -> None:
    """Near miss for the whole round: none of it shuts the ordinary path."""
    reviewer = draw()
    with harness(tmp_path, reviewer) as otp:
        otp.clock.advance(RESEND_COOLDOWN_S)
        assert answer(otp, DpopClient(), reviewer, ask(otp, reviewer)).status_code == 200
