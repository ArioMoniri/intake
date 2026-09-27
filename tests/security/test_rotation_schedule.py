"""INT-367 — scheduled quarterly KEK rotation and ``sec_secret_rotation_due_days``.

Acceptance, verbatim (GitHub #594):
  "a scheduled job runs the existing re-wrap rotation quarterly (files/10 §3)
   and emits sec_secret_rotation_due_days, catalogued as live; an overdue
   rotation raises an alert"

sec_row: data-at-rest · legal: 2018-10 (measure 3b, gap ``rotation-schedule``).

What is pinned here:
- **Cadence.** Quarterly is three calendar months (files/10 §3, "key rotation
  quarterly"), clamped to the month's length, counted from the moment the
  key's latest Transit version was created. That moment is read from OpenBao's
  own key metadata; nothing else stores it.
- **Near-miss control.** A key one second short of its quarter is left alone;
  at the quarter it is rotated.
- **Re-wrap only.** The job's only write is Transit ``rotate``, which adds a
  version. It never sets ``min_decryption_version``, never enables deletion,
  never deletes or trims, so a ciphertext written before a rotation — failed
  or successful — still decrypts, and ``rewrap_field`` moves it forward
  without touching the data bytes.
- **Signal.** ``sec_secret_rotation_due_days{key}`` carries a Transit key name
  and nothing else (invariant 6); it is catalogued ``live``; the overdue alert
  fires below zero and links its runbook.

The fake Transit extends the INT-014 fixture (``FakeTransit``) with the two
reads rotation needs and a clock for version timestamps. It lives in tests
only (invariant 17).
"""

from __future__ import annotations

import base64
import json
import re
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
import yaml
from intake_platform.envelope import EncryptedField, EnvelopeCipher, TransitKekProvider
from intake_platform.key_rotation import (
    ROTATION_PERIOD_MONTHS,
    SEC_SECRET_ROTATION_DUE_DAYS,
    KeyOutcome,
    RotationAction,
    RotationReport,
    TransitKekInventory,
    next_rotation_due,
    rotation_due_days,
    run_rotation,
)
from intake_platform.key_rotation.cli import EXIT_OK, EXIT_OVERDUE, EXIT_REFUSED, main
from intake_platform.secrets import SecretsProvider
from intake_platform.slo import load_metrics_catalog
from prometheus_client import REGISTRY
from test_envelope_transit_unit import FakeTransit

REPO = Path(__file__).resolve().parents[2]
SPEC = REPO / "files" / "10_SECURITY_AND_TECHNICAL_MONITORING.md"
CATALOG = REPO / "observability" / "metrics_catalog.yaml"
RULES = REPO / "infra" / "observability" / "security-rules.yaml"
PROMETHEUS = REPO / "infra" / "observability" / "prometheus.yml"
OBS_COMPOSE = REPO / "infra" / "docker-compose.obs.yml"
MAKEFILE = REPO / "Makefile"

METRIC = "sec_secret_rotation_due_days"
T0 = datetime(2026, 1, 15, 3, 0, tzinfo=UTC)
DAY = 86_400.0


# --- the fake Transit ---------------------------------------------------------------


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def epoch(self) -> int:
        return int(self.now.timestamp())


class ClockedTransit(FakeTransit):
    """INT-014's FakeTransit, plus: LIST and read of key metadata with a
    creation time per version, ``min_decryption_version`` honoured on decrypt,
    a switch that makes ``rotate`` fail for a named key, and a call log."""

    def __init__(self, clock: Clock) -> None:
        super().__init__()
        self.clock = clock
        self.created: dict[str, dict[int, int]] = {}
        self.min_decryption: dict[str, int] = {}
        self.fail_rotate: set[str] = set()
        self.calls: list[tuple[str, str]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.calls.append((request.method, path))
        parts = path.split("/")
        name = parts[4] if len(parts) > 4 else ""
        if request.method == "GET" and path == "/v1/transit/keys":
            if request.url.params.get("list") != "true":
                return httpx.Response(405)
            if not self.keys:
                return httpx.Response(404, json={"errors": []})
            return httpx.Response(200, json={"data": {"keys": sorted(self.keys)}})
        if request.method == "GET" and path == f"/v1/transit/keys/{name}":
            if name not in self.keys:
                return httpx.Response(404, json={"errors": []})
            return httpx.Response(200, json={"data": self._metadata(name)})
        if request.method == "POST" and path == f"/v1/transit/keys/{name}/rotate":
            if name in self.fail_rotate:
                return httpx.Response(500, json={"errors": ["storage write failed"]})
            response = super().handler(request)
            self.created[name][self.keys[name]] = self.clock.epoch()
            return response
        if request.method == "POST" and path == f"/v1/transit/keys/{name}/config":
            body = json.loads(request.content or b"{}")
            if "min_decryption_version" in body:
                self.min_decryption[name] = int(body["min_decryption_version"])
            return super().handler(request)
        if request.method == "POST" and path == f"/v1/transit/keys/{name}":
            fresh = name not in self.keys
            response = super().handler(request)
            if fresh:
                self.created[name] = {1: self.clock.epoch()}
            return response
        if request.method == "POST" and path == f"/v1/transit/decrypt/{name}":
            ciphertext = json.loads(request.content)["ciphertext"]
            version = int(ciphertext.split(":")[1][1:])
            if version < self.min_decryption.get(name, 1):
                return httpx.Response(400, text="ciphertext version is disallowed by policy")
        return super().handler(request)

    def _metadata(self, name: str) -> dict[str, object]:
        return {
            "name": name,
            "type": "aes256-gcm96",
            "deletion_allowed": name in self.deletion_allowed,
            "latest_version": self.keys[name],
            "min_decryption_version": self.min_decryption.get(name, 1),
            "min_encryption_version": 0,
            "keys": {str(version): at for version, at in sorted(self.created[name].items())},
        }

    def writes_by_the_job(self) -> set[tuple[str, str]]:
        """Every non-read request, minus the test's own encrypt/decrypt calls."""
        return {
            (method, path)
            for method, path in self.calls
            if method != "GET"
            and not path.startswith(("/v1/transit/encrypt/", "/v1/transit/decrypt/"))
        }


def _secrets(fake: ClockedTransit) -> SecretsProvider:
    secrets = SecretsProvider(addr="http://transit.test", token="unit")
    secrets._client = httpx.Client(
        base_url="http://transit.test", transport=httpx.MockTransport(fake.handler)
    )
    return secrets


class World:
    """One OpenBao, one clock, the envelope cipher the API uses, the job's two ports."""

    def __init__(self, start: datetime = T0) -> None:
        self.clock = Clock(start)
        self.transit = ClockedTransit(self.clock)
        self.secrets = _secrets(self.transit)
        self.kek = TransitKekProvider(self.secrets)
        self.cipher = EnvelopeCipher(self.kek)
        self.inventory = TransitKekInventory(self.secrets)

    def write(self, tenant_id: str, plaintext: bytes) -> EncryptedField:
        return self.cipher.encrypt_field(tenant_id, plaintext, aad=b"notes.v1")

    def read(self, tenant_id: str, field: EncryptedField) -> bytes:
        return self.cipher.decrypt_field(tenant_id, field, aad=b"notes.v1")

    def tick(self, at: datetime) -> RotationReport:
        self.clock.now = at
        return run_rotation(self.inventory, self.kek, now=at)


def _gauge(key: str) -> float | None:
    return REGISTRY.get_sample_value(METRIC, {"key": key})


def _outcome(report: RotationReport, key: str) -> KeyOutcome:
    return next(outcome for outcome in report.outcomes if outcome.key_id == key)


# --- cadence ------------------------------------------------------------------------


def test_the_cadence_is_quarterly_as_files_10_s3_states() -> None:
    text = SPEC.read_text(encoding="utf-8")
    section = text[text.index("\n## 3.") : text.index("\n## 4.")]
    assert "key rotation quarterly" in section, "files/10 §3 no longer states the cadence"
    assert ROTATION_PERIOD_MONTHS == 3


@pytest.mark.parametrize(
    ("last", "due"),
    [
        (datetime(2026, 1, 15, 3, 0, tzinfo=UTC), datetime(2026, 4, 15, 3, 0, tzinfo=UTC)),
        # across the year, and clamped to the shorter month rather than spilling over
        (datetime(2026, 11, 30, 9, 0, tzinfo=UTC), datetime(2027, 2, 28, 9, 0, tzinfo=UTC)),
        (datetime(2027, 11, 30, 9, 0, tzinfo=UTC), datetime(2028, 2, 29, 9, 0, tzinfo=UTC)),
        # an offset instant is the same instant: the months are counted in UTC
        # (29 Nov 22:00 UTC), not on the +03 wall clock (30 Nov 01:00)
        (
            datetime(2026, 11, 30, 1, 0, tzinfo=timezone(timedelta(hours=3))),
            datetime(2027, 2, 28, 22, 0, tzinfo=UTC),
        ),
    ],
)
def test_next_due_is_three_calendar_months_on(last: datetime, due: datetime) -> None:
    assert next_rotation_due(last) == due


def test_due_days_counts_down_and_goes_negative_once_overdue() -> None:
    last = datetime(2026, 1, 1, tzinfo=UTC)  # due 2026-04-01
    assert rotation_due_days(last, datetime(2026, 3, 22, tzinfo=UTC)) == 10.0
    assert rotation_due_days(last, datetime(2026, 4, 1, tzinfo=UTC)) == 0.0
    assert rotation_due_days(last, datetime(2026, 4, 3, 12, tzinfo=UTC)) == -2.5


def test_a_naive_instant_is_refused() -> None:
    with pytest.raises(ValueError, match="tz-aware"):
        next_rotation_due(datetime(2026, 1, 1))
    with pytest.raises(ValueError, match="tz-aware"):
        rotation_due_days(T0, datetime(2026, 1, 1))


# --- the job: due-ness from Transit metadata ------------------------------------------


def test_a_current_key_is_left_alone_and_reports_its_countdown() -> None:
    world = World()
    world.write("a", b"note")
    report = world.tick(T0 + timedelta(days=30))

    assert _outcome(report, "tenant-a").action is RotationAction.CURRENT
    assert world.transit.keys["tenant-a"] == 1
    assert _gauge("tenant-a") == (datetime(2026, 4, 15, 3, 0, tzinfo=UTC) - world.clock.now) / (
        timedelta(days=1)
    )
    assert world.transit.writes_by_the_job() == {("POST", "/v1/transit/keys/tenant-a")}, (
        "a key that is not due must see reads only (the one POST is the test's own first wrap)"
    )
    assert report.ok


def test_near_miss_one_second_short_of_the_quarter_is_not_rotated_but_the_quarter_is() -> None:
    world = World()
    world.write("a", b"note")
    due = next_rotation_due(T0)

    short = world.tick(due - timedelta(seconds=1))
    assert _outcome(short, "tenant-a").action is RotationAction.CURRENT
    assert world.transit.keys["tenant-a"] == 1
    assert _gauge("tenant-a") == pytest.approx(1 / DAY)

    on_time = world.tick(due)
    assert _outcome(on_time, "tenant-a").action is RotationAction.ROTATED
    assert world.transit.keys["tenant-a"] == 2


def test_an_overdue_key_is_rotated_and_its_countdown_restarts_from_transit() -> None:
    world = World()
    world.write("a", b"note")
    late = next_rotation_due(T0) + timedelta(days=5)

    report = world.tick(late)

    outcome = _outcome(report, "tenant-a")
    assert outcome.action is RotationAction.ROTATED
    assert outcome.key_version == 2
    # the new version's creation time is Transit's, and it is `late`
    assert world.transit.created["tenant-a"][2] == int(late.timestamp())
    expected = (next_rotation_due(late) - late) / timedelta(days=1)
    assert outcome.due_days == expected
    assert _gauge("tenant-a") == expected
    assert report.ok

    # the next tick, a day later, finds it current: one rotation per quarter
    again = world.tick(late + timedelta(days=1))
    assert _outcome(again, "tenant-a").action is RotationAction.CURRENT
    assert world.transit.keys["tenant-a"] == 2


def test_only_envelope_keks_are_rotated_and_labelled() -> None:
    world = World()
    world.write("a", b"note")
    # the identity vault's key (INT-013) is a Transit key too, but not a tenant KEK
    world.transit.keys["tokenization"] = 1
    world.transit.created["tokenization"] = {1: world.clock.epoch()}

    report = world.tick(T0 + timedelta(days=400))

    assert [outcome.key_id for outcome in report.outcomes] == ["tenant-a"]
    assert world.transit.keys["tokenization"] == 1
    assert _gauge("tokenization") is None


def test_the_gauge_carries_the_transit_key_name_and_nothing_else() -> None:
    world = World()
    world.write("7f1c3a52-0000-4000-8000-000000000001", b"note")
    world.tick(T0 + timedelta(days=1))

    samples = [
        sample
        for family in REGISTRY.collect()
        if family.name == METRIC
        for sample in family.samples
    ]
    assert [sample.labels for sample in samples] == [
        {"key": "tenant-7f1c3a52-0000-4000-8000-000000000001"}
    ]


def test_a_key_that_disappeared_stops_being_reported() -> None:
    world = World()
    world.write("a", b"note")
    world.write("b", b"note")
    world.tick(T0 + timedelta(days=1))
    assert _gauge("tenant-b") is not None

    del world.transit.keys["tenant-b"]  # crypto-shredded tenant (INT-014 destroy)
    world.tick(T0 + timedelta(days=2))
    assert _gauge("tenant-b") is None
    assert _gauge("tenant-a") is not None


# --- re-wrap only: nothing is destroyed or orphaned ------------------------------------


def test_a_failed_rotation_stays_overdue_and_every_ciphertext_still_decrypts() -> None:
    world = World()
    note_a = world.write("a", b"tenant a's note")
    note_b = world.write("b", b"tenant b's note")
    world.transit.fail_rotate.add("tenant-a")
    late = next_rotation_due(T0) + timedelta(days=2)

    report = world.tick(late)

    assert _outcome(report, "tenant-a").action is RotationAction.FAILED
    assert _outcome(report, "tenant-b").action is RotationAction.ROTATED
    assert not report.ok
    # the failed key keeps reading overdue, which is what the alert fires on
    assert _gauge("tenant-a") == -2.0
    assert _gauge("tenant-b") > 0
    # nothing written before the run was orphaned, on either side of the failure
    assert world.read("a", note_a) == b"tenant a's note"
    assert world.read("b", note_b) == b"tenant b's note"
    assert world.read("a", world.write("a", b"after")) == b"after"


def test_rotation_keeps_old_versions_so_pre_rotation_ciphertext_decrypts_and_rewraps() -> None:
    world = World()
    before = world.write("a", b"written in january")
    world.tick(next_rotation_due(T0))
    world.tick(next_rotation_due(next_rotation_due(T0)))
    assert world.transit.keys["tenant-a"] == 3

    assert world.transit.min_decryption.get("tenant-a", 1) == 1
    assert world.read("a", before) == b"written in january"
    moved = world.cipher.rewrap_field("a", before)
    assert moved.key_version == 3
    assert moved.ciphertext == before.ciphertext, "a rewrap must never re-encrypt the data"
    assert world.read("a", moved) == b"written in january"


def test_the_job_never_calls_a_destructive_transit_endpoint() -> None:
    world = World()
    world.write("a", b"note")
    world.write("b", b"note")
    world.transit.fail_rotate.add("tenant-b")
    world.tick(next_rotation_due(T0) + timedelta(days=1))

    job_writes = world.transit.writes_by_the_job() - {
        ("POST", "/v1/transit/keys/tenant-a"),
        ("POST", "/v1/transit/keys/tenant-b"),
    }  # the two first wraps are the test's own
    assert job_writes == {
        ("POST", "/v1/transit/keys/tenant-a/rotate"),
        ("POST", "/v1/transit/keys/tenant-b/rotate"),
    }
    assert world.transit.deletion_allowed == set()


def test_unreadable_metadata_is_reported_and_never_guessed() -> None:
    world = World()
    world.write("a", b"note")
    world.write("b", b"note")
    world.transit.created["tenant-b"] = {}  # the latest version has no creation time

    report = world.tick(next_rotation_due(T0) + timedelta(days=1))

    assert _outcome(report, "tenant-b").action is RotationAction.UNREADABLE
    assert _outcome(report, "tenant-b").due_days is None
    assert _gauge("tenant-b") is None
    assert world.transit.keys["tenant-b"] == 1, "a key whose age is unknown is not rotated blind"
    assert _outcome(report, "tenant-a").action is RotationAction.ROTATED
    assert not report.ok


def test_a_creation_time_that_is_not_epoch_seconds_is_unreadable() -> None:
    """Asymmetric Transit keys report an RFC 3339 string per version; a KEK
    that ever answered that way is not parsed as a time it is not."""
    world = World()
    world.write("a", b"note")
    world.transit.created["tenant-a"] = {1: "2026-01-15T03:00:00Z"}  # type: ignore[dict-item]

    report = world.tick(next_rotation_due(T0) + timedelta(days=1))

    assert _outcome(report, "tenant-a").action is RotationAction.UNREADABLE
    assert world.transit.keys["tenant-a"] == 1


@pytest.mark.parametrize(
    "body",
    [{"data": {"keys": "tenant-a"}}, {"data": {"keys": [1, 2]}}, {"data": None}, {}],
)
def test_a_malformed_key_list_is_refused_not_read_as_empty(
    body: dict[str, object], capsys: pytest.CaptureFixture[str]
) -> None:
    secrets = SecretsProvider(addr="http://transit.test", token="unit")
    secrets._client = httpx.Client(
        base_url="http://transit.test",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body)),
    )

    assert main([], secrets=secrets, clock=lambda: T0) == EXIT_REFUSED
    assert "refused" in capsys.readouterr().out


def test_a_rotate_that_transit_did_not_record_is_a_failure() -> None:
    world = World()
    world.write("a", b"note")
    late = next_rotation_due(T0) + timedelta(days=1)

    class SilentRotator:
        def rotate(self, tenant_id: str) -> None:
            del tenant_id  # answers without rotating anything

    world.clock.now = late
    report = run_rotation(world.inventory, SilentRotator(), now=late)

    assert _outcome(report, "tenant-a").action is RotationAction.FAILED
    assert _gauge("tenant-a") == -1.0


# --- the catalogue and the alert --------------------------------------------------------


def test_the_catalogue_lists_the_gauge_as_live_with_a_key_label() -> None:
    entry = next(m for m in load_metrics_catalog(CATALOG).metrics if m.name == METRIC)
    assert entry.status == "live"
    assert entry.type == "gauge"
    assert entry.labels == ["key"]
    assert entry.unit == "days"
    assert SEC_SECRET_ROTATION_DUE_DAYS._name == METRIC  # the family the job sets


def _rules() -> dict[str, dict[str, object]]:
    groups = yaml.safe_load(RULES.read_text(encoding="utf-8"))["groups"]
    return {rule["alert"]: rule for group in groups for rule in group["rules"] if "alert" in rule}


def test_the_overdue_alert_fires_below_zero_and_links_its_runbook() -> None:
    rule = _rules()["SecretRotationOverdue"]
    assert rule["expr"] == f"{METRIC} < 0"
    assert load_metrics_catalog(CATALOG).unknown_references(str(rule["expr"])) == frozenset()
    annotations = rule["annotations"]
    assert isinstance(annotations, dict)
    runbook, _, anchor = str(annotations["runbook"]).partition("#")
    text = (REPO / runbook).read_text(encoding="utf-8")
    headings = {
        re.sub(r"[^a-z0-9 -]", "", line.lstrip("#").strip().lower()).replace(" ", "-")
        for line in text.splitlines()
        if line.startswith("#")
    }
    assert anchor in headings, f"{runbook} has no heading for #{anchor}"


def test_prometheus_loads_the_security_rule_file() -> None:
    config = yaml.safe_load(PROMETHEUS.read_text(encoding="utf-8"))
    assert "/etc/prometheus/rules/security-rules.yaml" in config["rule_files"]
    compose = yaml.safe_load(OBS_COMPOSE.read_text(encoding="utf-8"))
    volumes = [str(v) for v in compose["services"]["prometheus"]["volumes"]]
    assert (
        "./observability/security-rules.yaml:/etc/prometheus/rules/security-rules.yaml:ro"
        in volumes
    )


# --- the scheduled entry point ------------------------------------------------------------


def test_the_make_target_runs_one_tick_of_the_job() -> None:
    makefile = MAKEFILE.read_text(encoding="utf-8")
    target = re.search(r"^key-rotation:\n((?:\t.*\n)+)", makefile, re.M)
    assert target is not None, "no key-rotation target"
    assert "python -m intake_platform.key_rotation" in target.group(1)


def test_cli_tick_rotates_what_is_due_and_prints_ids_only(
    capsys: pytest.CaptureFixture[str],
) -> None:
    world = World()
    world.write("a", b"patient words stay out of the output")
    world.write("b", b"note")
    world.clock.now = T0 + timedelta(days=1)
    world.write("c", b"note")  # created a day later: still current at the tick

    tick_at = next_rotation_due(T0) + timedelta(hours=1)
    world.clock.now = tick_at
    code = main([], secrets=world.secrets, clock=lambda: tick_at)

    out = capsys.readouterr().out
    assert code == EXIT_OK
    assert "3 envelope KEKs — 2 rotated, 1 current, 0 failed, 0 unreadable" in out
    assert "tenant-a  rotated" in out
    assert "tenant-c  current" in out
    assert "patient" not in out
    assert base64.b64encode(b"patient").decode() not in out


def test_cli_exits_overdue_when_a_rotation_fails(capsys: pytest.CaptureFixture[str]) -> None:
    world = World()
    world.write("a", b"note")
    world.transit.fail_rotate.add("tenant-a")
    world.clock.now = next_rotation_due(T0)

    code = main([], secrets=world.secrets, clock=lambda: world.clock.now)

    assert code == EXIT_OVERDUE
    assert "tenant-a  failed" in capsys.readouterr().out


def test_cli_refuses_without_an_openbao_pointer(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("INTAKE_ENV", "dev")
    monkeypatch.delenv("OPENBAO_TOKEN", raising=False)

    code = main([])

    assert code == EXIT_REFUSED
    assert "refused" in capsys.readouterr().out


def test_cli_refuses_when_the_key_list_cannot_be_read(
    capsys: pytest.CaptureFixture[str],
) -> None:
    broken = SecretsProvider(addr="http://transit.test", token="unit")
    broken._client = httpx.Client(
        base_url="http://transit.test",
        transport=httpx.MockTransport(lambda request: httpx.Response(503)),
    )

    code = main([], secrets=broken, clock=lambda: T0)

    assert code == EXIT_REFUSED
    assert "refused" in capsys.readouterr().out
