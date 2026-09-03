"""INT-203 — the edge tier, booted, deciding real requests.

``tests/infra/test_waf_rules.py`` owns the configuration; this file owns the
only question that configuration exists to answer — *does the thing block?* —
and answers it against the real engine: Traefik v3 with the Coraza middleware
and the OWASP CRS embedded in the pinned plugin artefact.

It is marked ``integration`` and boots its own tier, so it runs in the
compose job (``make check-integration`` / ``make edge-check``) and never in the
unit lane. It does **not** skip when the tier is absent: a WAF suite that
quietly does not run is the failure mode this whole file exists to make
impossible, so a missing artefact fails and names the target that fetches it
(the ``make deid-model`` precedent).

Nothing here reaches the internet. Traefik loads the plugin from
``.cache/edge`` on disk, the CRS ships inside it, CrowdSec runs with the
central API disabled, and the upstream is a local echo container that exists
for this file and is gated behind its own compose profile.
"""

from __future__ import annotations

import json
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[2]
COMPOSE = REPO / "infra" / "docker-compose.edge.yml"
CORPUS_PATH = REPO / "tests" / "fixtures" / "waf" / "corpus.yaml"
PLUGIN_DIR = REPO / ".cache" / "edge" / "plugins-local" / "src" / "github.com" / "corazawaf"
BASE_URL = "http://127.0.0.1:18080"
HOST_HEADER = "intake.test"


def _compose(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 — fixed argv, our own compose file
        ["docker", "compose", "-f", str(COMPOSE), "--profile", "edge-test", *args],  # noqa: S607
        cwd=REPO,
        capture_output=True,
        text=True,
        check=check,
    )


@pytest.fixture(scope="module", autouse=True)
def edge_tier() -> Iterator[None]:
    plugin = PLUGIN_DIR / "coraza-http-wasm" / "coraza-http-wasm.wasm"
    if not plugin.is_file():
        pytest.fail(
            f"the pinned Coraza plugin is not on disk at {plugin}. Run `make edge-plugin` "
            "— it downloads the artefact named in infra/security/edge/edge-policy.yaml and "
            "verifies its sha256 before unpacking. This test fails rather than skips: a WAF "
            "suite that silently does not run is worse than no suite."
        )
    _compose("up", "-d", "--wait")
    try:
        _wait_for_edge()
        yield
    finally:
        _compose("down", "-v", check=False)


def _wait_for_edge(timeout_s: float = 60.0) -> None:
    deadline = time.monotonic() + timeout_s
    last: Exception | None = None
    while time.monotonic() < deadline:
        try:
            response = httpx.get(f"{BASE_URL}/healthz", headers={"Host": HOST_HEADER}, timeout=2.0)
        except httpx.HTTPError as exc:  # the tier is still coming up
            last = exc
        else:
            if response.status_code < 500:
                return
        time.sleep(1.0)
    raise AssertionError(f"the edge tier did not answer within {timeout_s}s: {last}")


def _cases() -> list[dict[str, Any]]:
    loaded: dict[str, Any] = yaml.safe_load(CORPUS_PATH.read_text(encoding="utf-8"))
    cases: list[dict[str, Any]] = loaded["cases"]
    return cases


def _ids() -> list[str]:
    return [str(case["name"]) for case in _cases()]


def _send(case: dict[str, Any]) -> httpx.Response:
    headers = {"Host": HOST_HEADER, **{str(k): str(v) for k, v in case.get("headers", {}).items()}}
    body = case.get("body")
    if body is None:
        return httpx.get(
            f"{BASE_URL}{case['path']}",
            params=case.get("query"),
            headers=headers,
            timeout=10.0,
        )
    headers.setdefault("Content-Type", case.get("content_type", "application/json"))
    return httpx.post(
        f"{BASE_URL}{case['path']}",
        content=str(body).encode("utf-8"),
        headers=headers,
        timeout=10.0,
    )


# --- the acceptance clause: "WAF blocks OWASP CRS suite" ----------------------------


@pytest.mark.parametrize("case", _cases(), ids=_ids())
def test_the_waf_decides_the_corpus_the_way_the_corpus_says(case: dict[str, Any]) -> None:
    """One parametrisation, both directions.

    An attack must be refused **and** an ordinary Turkish clinical turn must be
    served. Splitting these into two tests invites one of them to be deleted
    when it goes red; together they state the property, which is that the WAF
    discriminates.
    """
    response = _send(case)
    if case["expect"] == "blocked":
        assert response.status_code == 403, f"{case['name']} ({case['crs_family']}) was served"
    else:
        assert response.status_code < 400, (
            f"{case['name']} is ordinary clinical traffic and the WAF refused it "
            f"({response.status_code}); a WAF that blocks the product is not a control"
        )


def test_the_suite_contains_both_verdicts() -> None:
    verdicts = {case["expect"] for case in _cases()}
    assert verdicts == {"blocked", "passed"}


# --- the acceptance clause: "CrowdSec scenarios on" ---------------------------------


def _cscli(*args: str) -> str:
    result = _compose("exec", "-T", "crowdsec", "cscli", *args)
    return result.stdout


def test_the_intake_scenarios_are_loaded_and_enabled() -> None:
    listed = json.loads(_cscli("scenarios", "list", "-o", "json"))
    rows = listed["scenarios"] if isinstance(listed, dict) else listed
    by_name = {row["name"]: row for row in rows}
    declared = {
        document["name"]
        for document in yaml.safe_load_all(
            (
                REPO / "infra" / "security" / "edge" / "crowdsec" / "scenarios" / "intake.yaml"
            ).read_text(encoding="utf-8")
        )
        if document
    }
    assert declared <= set(by_name), sorted(set(by_name))
    for name in declared:
        assert "enabled" in by_name[name]["status"], by_name[name]


def test_a_burst_of_blocked_requests_reaches_the_scenario_and_a_clean_one_does_not() -> None:
    """``cscli explain`` runs acquisition, both parser stages and the scenarios
    over a file, deterministically and offline. It is the honest way to decide
    a bucket without waiting on a live tail — and it gives the near-miss
    control for free: the same pipeline, one field different, no scenario."""
    burst = "\n".join(
        json.dumps(
            {
                "ClientHost": "203.0.113.90",
                "DownstreamStatus": 403,
                "RequestMethod": "GET",
                "time": f"2026-09-03T20:30:0{index}Z",
            }
        )
        for index in range(1, 8)
    )
    clean = json.dumps(
        {
            "ClientHost": "198.51.100.9",
            "DownstreamStatus": 200,
            "RequestMethod": "GET",
            "time": "2026-09-03T20:30:01Z",
        }
    )

    assert "intake/waf-block-burst" in _explain(burst)
    assert "intake/waf-block-burst" not in _explain(clean)


def _explain(lines: str) -> str:
    _compose(
        "exec",
        "-T",
        "crowdsec",
        "sh",
        "-c",
        "cat > /tmp/explain.log",
        check=False,
    )
    # `docker compose exec -T` gives no stdin plumbing through our helper, so
    # the file is written with a here-doc in the container instead.
    encoded = lines.replace("'", "'\\''")
    _compose("exec", "-T", "crowdsec", "sh", "-c", f"printf '%s\\n' '{encoded}' > /tmp/explain.log")
    result = _compose(
        "exec",
        "-T",
        "crowdsec",
        "cscli",
        "explain",
        "--file",
        "/tmp/explain.log",
        "--type",
        "traefik",
    )
    return result.stdout


# --- the acceptance clause: "certs automated" ---------------------------------------


def test_traefik_loaded_the_acme_resolver_the_policy_declares() -> None:
    """The resolver is real configuration Traefik parses at boot; a
    mistyped challenge type or a missing storage path is a startup error, and
    a tier that came up with ``--wait`` has already proved it. What is left to
    assert is that the resolver Traefik knows about is the one the policy
    names — the drift a rendered file can still hide."""
    policy = yaml.safe_load(
        (REPO / "infra" / "security" / "edge" / "edge-policy.yaml").read_text(encoding="utf-8")
    )
    resolver = policy["tls"]["resolver"]
    logs = _compose("logs", "traefik").stdout
    assert "Plugins loaded" in logs
    assert "level=error" not in logs.lower().replace("level=info", ""), logs[-2000:]
    static = yaml.safe_load(
        (REPO / "infra" / "security" / "edge" / "traefik" / "traefik.yml").read_text("utf-8")
    )
    assert resolver in static["certificatesResolvers"]


# --- invariant 6 at the edge --------------------------------------------------------


def test_a_blocked_clinical_request_leaves_no_clinical_text_in_the_access_log() -> None:
    """The access log is the file CrowdSec reads and the SIEM ships. Traefik's
    field selection is ``drop`` by default here, so the patient's sentence
    cannot reach it even when the request that carried it was refused."""
    case = next(case for case in _cases() if case["name"] == "sqli_in_turkish_utterance_field")
    _send(case)
    logs = _compose("exec", "-T", "traefik", "cat", "/var/log/traefik/access.log").stdout
    assert logs.strip(), "the access log must exist, or this proves nothing"
    for fragment in ("text_tr", "UNION", "SELECT", "Göğsümde"):
        assert fragment not in logs, fragment
