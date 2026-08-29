"""INT-145 — the shipped-source guard over the mobile crash reporter.

The backlog names this file (`tests: [tests/mobile/test_crash_scrub.py]`). It
cannot execute the TypeScript scrubber, and it does not try to: the behavioural
proof — four planted identifiers, one near-miss control — lives next to the code
in ``apps/mobile/src/lib/telemetry/scrub.test.ts`` and runs under
``pnpm vitest run``. What a Python test *can* prove, and what no vitest
assertion can, is a property of the source itself:

  the crash reporter reads a **closed, enumerated set of keys** out of the
  untrusted crash event, and that set is recorded here.

That is the difference between a deny-by-default allow-list and a blocklist.
A blocklist is a claim about the payloads someone imagined; an allow-list is a
claim about the code, and this file is where widening it becomes visible. Add a
key to the reader and this test fails until the new key is written down and
justified — which is exactly the review moment invariant 6 needs.

The remaining tests hold the properties files/10 §3–§4 name for a crash
reporter: no default endpoint, nothing on disk, and session replay and
screenshot capture absent from the tree rather than merely switched off.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
TELEMETRY = REPO / "apps" / "mobile" / "src" / "lib" / "telemetry"

# Every key the scrubber is allowed to read out of an untrusted crash event.
# Reads go through the readString/readNumber/readArray/readRecord helpers, so
# this set is mechanically recoverable from the source (see _read_keys).
EXPECTED_READ_KEYS = frozenset(
    {
        # the event's own limbs
        "errorCode",
        "exception",
        "breadcrumbs",
        "tags",
        "timestampMs",
        # exception -> values[] -> stacktrace -> frames[]
        "values",
        "type",
        "stacktrace",
        "frames",
        # one frame: code coordinates only, never `vars` or a context line
        "module",
        "function",
        "lineno",
        "colno",
        # one breadcrumb: a category, an event code, a route template, a status
        "category",
        "event",
        "route",
        "status",
    }
)

# The tag allow-list, split by who may supply each key. Identity keys come from
# the client's own construction; event keys are the only ones a crash event may
# set, and each carries its own value shape.
EXPECTED_IDENTITY_TAG_KEYS = (
    "app_version",
    "build_id",
    "sbom_digest",
    "environment",
    "release_channel",
    "platform",
    "os_version",
    "device_model",
    "tenant_id",
)
EXPECTED_EVENT_TAG_KEYS = (
    "session_id_hash",
    "protocol_hash",
    "prompt_version",
    "screen_id",
)

# Capture surfaces that must not exist in the tree at all (files/10 §4: crash
# reports without PHI). "Unreachable, not merely unconfigured" means there is
# no code path to reach, so the words are absent from the shipped modules.
FORBIDDEN_CAPTURE_TOKENS = (
    "replay",
    "screenshot",
    "attachment",
    "captureScreen",
    "viewHierarchy",
    "profilesSampleRate",
)

# Anything that would put a crash event on disk. Invariant 3's posture is that
# nothing sensitive lands on storage; a reporter that buffers events to disk
# while offline is precisely that, and it is why this client drops instead.
FORBIDDEN_PERSISTENCE_TOKENS = (
    "expo-file-system",
    "expo-secure-store",
    "AsyncStorage",
    "localStorage",
    "sessionStorage",
    "node:fs",
)

_READ_HELPER = re.compile(r"\bread(?:String|Number|Array|Record)\s*\(\s*[^,]+,\s*\"([^\"]+)\"")
_ARRAY_LITERAL = r"const\s+{name}\s*(?::[^=]+)?=\s*\[(.*?)\]"
_OBJECT_LITERAL = r"const\s+{name}\s*(?::[^=]+)?=\s*\{{(.*?)\n\}};"
_STRING_ITEM = re.compile(r"\"([^\"]+)\"")
_OBJECT_KEY = re.compile(r"^\s{2}([A-Za-z_][A-Za-z0-9_]*):", re.M)


def _shipped_sources() -> list[Path]:
    """Every module the app ships — the colocated *.test.ts files excluded."""
    return sorted(p for p in TELEMETRY.glob("*.ts") if not p.name.endswith(".test.ts"))


def _source(name: str) -> str:
    return (TELEMETRY / name).read_text(encoding="utf-8")


def _code_only(text: str) -> str:
    """Strip comments so the guards below scan code, not prose.

    The modules explain at length why session replay and screenshot capture do
    not exist here; that explanation is the point and must not itself trip the
    guard. A line comment is only recognised after start-of-line or whitespace,
    so a `://` inside a string literal survives for the endpoint scan.
    """
    without_blocks = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"(?m)(^|\s)//.*$", r"\1", without_blocks)


def _read_keys() -> frozenset[str]:
    return frozenset(_READ_HELPER.findall(_source("scrub.ts")))


def _string_array(source: str, name: str) -> tuple[str, ...]:
    match = re.search(_ARRAY_LITERAL.format(name=name), source, re.S)
    assert match is not None, f"{name} is not a literal array in scrub.ts"
    return tuple(_STRING_ITEM.findall(match.group(1)))


def _object_keys(source: str, name: str) -> tuple[str, ...]:
    match = re.search(_OBJECT_LITERAL.format(name=name), source, re.S)
    assert match is not None, f"{name} is not a literal object in scrub.ts"
    return tuple(_OBJECT_KEY.findall(match.group(1)))


def test_the_telemetry_modules_exist_and_are_colocated() -> None:
    names = {path.name for path in _shipped_sources()}
    assert {"scrub.ts", "envelope.ts", "dsn.ts", "client.ts", "metrics.ts", "webVitals.ts"} <= names


def test_the_scrubber_reads_a_closed_enumerated_key_set() -> None:
    """Deny by default: widening the reader has to be written down here."""
    read = _read_keys()
    assert read == EXPECTED_READ_KEYS, (
        "the crash scrubber's read set changed. Added keys: "
        f"{sorted(read - EXPECTED_READ_KEYS)}; removed: {sorted(EXPECTED_READ_KEYS - read)}. "
        "Every key read out of an untrusted crash event is an escape route for "
        "PHI (CLAUDE.md invariant 6) — record it here with its value shape."
    )


@pytest.mark.parametrize(
    "limb",
    ["message", "value", "vars", "extra", "contexts", "user", "request", "url", "data"],
    ids=lambda limb: f"never_reads_{limb}",
)
def test_the_free_text_limbs_are_never_read(limb: str) -> None:
    """The limbs that actually carry patient text in a real crash event.

    ``value`` is the exception message, ``vars`` the captured locals (files/10
    §3's pcm-buffer leak), ``message``/``data`` a breadcrumb's screen text and
    ``url`` a network breadcrumb's query string. None is on the read set.
    """
    assert limb not in _read_keys()


def test_the_tag_allow_list_is_a_literal_split_by_who_supplies_it() -> None:
    source = _source("scrub.ts")
    assert _string_array(source, "IDENTITY_TAG_KEYS") == EXPECTED_IDENTITY_TAG_KEYS
    assert _string_array(source, "EVENT_TAG_KEYS") == EXPECTED_EVENT_TAG_KEYS
    # The exported list the rest of the app sees is exactly the two joined —
    # never a third, wider list that the scrubber quietly honours.
    assert _string_array(source, "ALLOWED_TAG_KEYS") == ()


def test_every_allow_listed_tag_key_has_its_own_value_shape() -> None:
    """A key on the list is not enough. `05321234567` is a perfectly well-formed
    string, so a shared "any short token" shape would let a phone number ride in
    on a legitimate key name. Each key gets its own shape, and the shape table
    covers the allow-list exactly — no key without a shape, no shape without a
    key."""
    shaped = set(_object_keys(_source("scrub.ts"), "TAG_SHAPES"))
    assert shaped == set(EXPECTED_IDENTITY_TAG_KEYS) | set(EXPECTED_EVENT_TAG_KEYS)


@pytest.mark.parametrize("token", FORBIDDEN_CAPTURE_TOKENS)
def test_session_replay_and_screenshot_capture_are_absent_from_the_tree(token: str) -> None:
    for path in _shipped_sources():
        code = _code_only(path.read_text(encoding="utf-8")).lower()
        assert token.lower() not in code, (
            f"{path.name} has code reaching {token!r}: session replay and "
            "screenshot capture must be unreachable, not merely switched off"
        )


@pytest.mark.parametrize("token", FORBIDDEN_PERSISTENCE_TOKENS)
def test_no_crash_event_can_reach_the_disk(token: str) -> None:
    for path in _shipped_sources():
        assert token not in _code_only(path.read_text(encoding="utf-8")), (
            f"{path.name} reaches {token!r}: an unsent crash event is dropped, "
            "never buffered to storage (CLAUDE.md invariant 3's posture)"
        )


def test_there_is_no_default_endpoint_anywhere_in_the_client() -> None:
    """Unconfigured means inert. A fallback host would send crash events to
    somewhere nobody chose, which is the whole failure mode."""
    for path in _shipped_sources():
        code = _code_only(path.read_text(encoding="utf-8"))
        assert "http://" not in code and "https://" not in code, (
            f"{path.name} carries a literal endpoint"
        )


def test_the_adversarial_suite_plants_all_four_identifier_classes() -> None:
    suite = _source("scrub.test.ts")
    for planted, what in (
        ("Üç gündür göğsümde", "a Turkish symptom sentence"),
        ("05321234567", "a TR mobile number"),
        ("10000000146", "a checksum-valid TC Kimlik"),
        ("kan tahlili", "an uploaded document's title"),
    ):
        assert planted in suite, f"the scrub suite no longer plants {what}"
    # ...into every limb a real crash event has.
    for limb in ("message:", "vars:", "context_line:", "breadcrumbs:", "tags:", "extra:", "user:"):
        assert limb in suite, f"the scrub suite no longer plants into {limb}"
    # ...and keeps the control that makes a leak assertion falsifiable.
    assert "NEAR-MISS CONTROL" in suite


def test_the_client_metric_ids_are_the_catalogued_ones() -> None:
    """Invariant 13. These four ids already exist in the catalogue as
    `planned`; this client adds none and promotes none."""
    catalogue = (REPO / "observability" / "metrics_catalog.yaml").read_text(encoding="utf-8")
    for metric_id in (
        "client.crash_free_sessions",
        "client.cold_start_p95_ms",
        "client.anr_rate",
        "web.core_web_vitals",
    ):
        assert f"id: {metric_id}\n" in catalogue, f"{metric_id} is not catalogued"
        assert metric_id in _source("metrics.ts")
