"""INT-203 — the edge: WAF rules, CrowdSec scenarios, certificate automation.

Acceptance line under test, verbatim: *"WAF blocks OWASP CRS suite; CrowdSec
scenarios on; certs automated"*.

Three of those clauses are decisions somebody has to be able to re-take, so
this file decides them rather than asserting a file exists. The failure this
is written against is not "the ruleset is missing" — it is the pair of
failures that both *look* armed:

* a WAF that **blocks nothing**, because an exclusion was written wide
  (``ARGS`` rather than ``ARGS:json.text_tr``, ``/`` rather than one route) or
  because the anomaly threshold was raised until the alerts stopped;
* a WAF that **blocks everything**, which for this product means every
  Turkish clinical free-text turn — the exact traffic the system exists to
  carry, full of apostrophes (``Ali'nin``), angle brackets and words a naive
  signature reads as SQL.

So every group below carries a near-miss negative control, and the WAF's own
block/pass behaviour is decided against the real engine in
``tests/infra/test_edge_stack_integration.py`` (Traefik + Coraza + the
embedded OWASP CRS, booted), not modelled here. This file owns what is *ours*
and therefore reviewable without a container: the policy that configures that
engine, the rendered configuration that cannot drift from it, and the log
boundary — because a WAF that blocks a request and then writes the patient's
sentence into the edge log has traded an injection for a PHI disclosure
(CLAUDE.md invariant 6).
"""

from __future__ import annotations

import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml
from intake_platform.edge import (
    CRS_DEFAULT_INBOUND_THRESHOLD,
    EdgeEvent,
    EdgePolicy,
    EdgePolicyError,
    RuleClass,
    load_edge_policy,
    parse_coraza_line,
)
from pydantic import ValidationError

REPO = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO / "infra" / "security" / "edge" / "edge-policy.yaml"
RENDERER = REPO / "scripts" / "security" / "render_edge_conf.py"
TRAEFIK_STATIC = REPO / "infra" / "security" / "edge" / "traefik" / "traefik.yml"
TRAEFIK_DYNAMIC = REPO / "infra" / "security" / "edge" / "traefik" / "dynamic.yml"
CROWDSEC_DIR = REPO / "infra" / "security" / "edge" / "crowdsec"
CROWDSEC_SCENARIO_DIR = CROWDSEC_DIR / "scenarios"
CROWDSEC_PARSER = CROWDSEC_DIR / "parsers" / "s01-parse" / "traefik-access-log.yaml"
CERT_MANAGER = REPO / "infra" / "k8s" / "edge" / "cert-manager.yaml"
COMPOSE_PATH = REPO / "infra" / "docker-compose.edge.yml"
CORPUS_PATH = REPO / "tests" / "fixtures" / "waf" / "corpus.yaml"
CORAZA_LOG_FIXTURE = REPO / "tests" / "fixtures" / "waf" / "coraza-blocks.log"


def _policy() -> EdgePolicy:
    return load_edge_policy(POLICY_PATH)


def _raw_policy() -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))
    return loaded


def _write(tmp_path: Path, document: dict[str, Any]) -> Path:
    path = tmp_path / "edge-policy.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


# --- group 1: the WAF is armed, and armed means blocking -----------------------------


def test_the_shipped_policy_loads_and_the_engine_blocks() -> None:
    """``DetectionOnly`` is a WAF that logs an attack and serves it anyway."""
    assert _policy().waf.engine == "On"


def test_a_detection_only_engine_is_refused(tmp_path: Path) -> None:
    document = _raw_policy()
    document["waf"]["engine"] = "DetectionOnly"
    with pytest.raises(ValidationError):
        load_edge_policy(_write(tmp_path, document))


def test_the_inbound_threshold_only_ever_tightens() -> None:
    waf = _policy().waf
    assert 1 <= waf.inbound_anomaly_threshold <= CRS_DEFAULT_INBOUND_THRESHOLD
    assert waf.paranoia_level >= 1


def test_a_threshold_looser_than_the_crs_default_is_refused(tmp_path: Path) -> None:
    """Raising the threshold until the alerts stop is how a WAF is disarmed
    without anyone editing a rule."""
    document = _raw_policy()
    document["waf"]["inbound_anomaly_threshold"] = CRS_DEFAULT_INBOUND_THRESHOLD + 1
    with pytest.raises(ValidationError):
        load_edge_policy(_write(tmp_path, document))


def test_the_crs_version_is_pinned_and_matches_the_deployed_plugin() -> None:
    """The ruleset is embedded in the pinned wasm artefact; the policy states
    which version that is, so a plugin bump that changes the ruleset cannot be
    silent."""
    policy = _policy()
    assert policy.waf.crs_version.count(".") == 2, policy.waf.crs_version
    assert policy.waf.plugin_sha256 and len(policy.waf.plugin_sha256) == 64


# --- group 2: exclusions are the way a WAF is quietly turned off ---------------------


def test_every_exclusion_names_one_rule_on_one_route_at_one_target() -> None:
    for exclusion in _policy().waf.exclusions:
        assert 900000 <= exclusion.rule_id <= 999999, exclusion
        assert exclusion.route.startswith("/") and len(exclusion.route) > 1
        assert "*" not in exclusion.route
        assert ":" in exclusion.target, "a bare collection is an unbounded exclusion"
        assert exclusion.approval_ref
        assert exclusion.expires_on > date.today()


@pytest.mark.parametrize(
    ("field", "value", "why"),
    [
        ("route", "/", "the root route excludes the rule everywhere"),
        ("route", "/v1/*", "a glob route is an exclusion nobody can bound"),
        ("target", "ARGS", "a bare collection excludes every parameter"),
        ("target", "REQUEST_BODY", "the whole body is not a target, it is a surrender"),
        ("rule_id", 1, "not a CRS rule id"),
    ],
)
def test_a_wide_exclusion_is_refused(tmp_path: Path, field: str, value: object, why: str) -> None:
    document = _raw_policy()
    document["waf"]["exclusions"] = [
        {
            "rule_id": 942100,
            "route": "/v1/intake/utterance",
            "target": "ARGS:json.text_tr",
            "justification": "fixture",
            "approval_ref": "SEC-APPROVAL-FIXTURE",
            "expires_on": date(2099, 1, 1),
        }
    ]
    document["waf"]["exclusions"][0][field] = value
    with pytest.raises(ValidationError, match=".*"):
        load_edge_policy(_write(tmp_path, document))


def test_an_expired_exclusion_fails_the_load_rather_than_lingering(tmp_path: Path) -> None:
    document = _raw_policy()
    document["waf"]["exclusions"] = [
        {
            "rule_id": 942100,
            "route": "/v1/intake/utterance",
            "target": "ARGS:json.text_tr",
            "justification": "fixture",
            "approval_ref": "SEC-APPROVAL-FIXTURE",
            "expires_on": date(2020, 1, 1),
        }
    ]
    with pytest.raises(EdgePolicyError, match="expired"):
        load_edge_policy(_write(tmp_path, document))


# --- group 3: the rendered configuration cannot drift from the policy ----------------


def test_the_rendered_edge_configuration_is_current() -> None:
    """``make edge-conf-check``: the same arrangement INT-018 uses for the
    egress proxy — one source file, several generated ones, and a CI failure
    the moment a generated file is edited by hand."""
    result = subprocess.run(  # noqa: S603 — our own script, fixed argv
        [sys.executable, str(RENDERER), "--check"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_rendered_directives_carry_the_policy_and_the_whole_ruleset() -> None:
    directives = _coraza_directives()
    policy = _policy()
    assert f"SecRuleEngine {policy.waf.engine}" in directives
    assert "Include @coraza.conf-recommended" in directives
    assert "Include @crs-setup.conf.example" in directives
    assert "Include @owasp_crs/*.conf" in directives
    threshold = policy.waf.inbound_anomaly_threshold
    assert any(f"tx.inbound_anomaly_score_threshold={threshold}" in line for line in directives)


def test_every_policy_exclusion_reaches_the_rendered_directives() -> None:
    directives = _coraza_directives()
    for exclusion in _policy().waf.exclusions:
        assert any(
            str(exclusion.rule_id) in line and exclusion.target in line for line in directives
        ), exclusion


def test_no_rule_is_excluded_that_the_policy_did_not_declare() -> None:
    """The reverse direction, and the one that catches a hand-edit: a
    ``SecRuleRemoveById`` or ``SecRuleUpdateTargetById`` in the rendered file
    for a rule the policy never approved."""
    declared = {exclusion.rule_id for exclusion in _policy().waf.exclusions}
    for line in _coraza_directives():
        if line.startswith(("SecRuleRemoveById", "SecRuleUpdateTargetById")):
            found = {int(token) for token in line.split() if token.isdigit()}
            assert found <= declared, line


def _coraza_directives() -> list[str]:
    document = yaml.safe_load(TRAEFIK_DYNAMIC.read_text(encoding="utf-8"))
    middlewares = document["http"]["middlewares"]
    directives: list[str] = middlewares["intake-waf"]["plugin"]["coraza"]["directives"]
    return directives


# --- group 4: the corpus this WAF is judged against ----------------------------------


def _corpus() -> list[dict[str, Any]]:
    loaded: dict[str, Any] = yaml.safe_load(CORPUS_PATH.read_text(encoding="utf-8"))
    cases: list[dict[str, Any]] = loaded["cases"]
    return cases


def test_the_corpus_covers_the_crs_attack_families_and_the_near_misses() -> None:
    cases = _corpus()
    blocked = {case["crs_family"] for case in cases if case["expect"] == "blocked"}
    # One family per CRS REQUEST-9xx file the acceptance's "OWASP CRS suite"
    # means in practice.
    assert {"sqli", "xss", "lfi", "rce", "scanner", "protocol"} <= blocked
    passed = [case for case in cases if case["expect"] == "passed"]
    assert len(passed) >= 4, "a suite with no negative controls proves nothing"


def test_the_negative_controls_are_actually_clinical_turkish() -> None:
    """A near-miss that is not near enough is a control that never fires. Each
    passing case must carry at least one of the things that trips a naive
    signature on Turkish clinical prose."""
    tripwires = ("'", "<", ">", "&", "--", "1=1", "select")
    for case in _corpus():
        if case["expect"] != "passed":
            continue
        body = str(case.get("body", "")) + str(case.get("query", ""))
        assert any(token in body.lower() for token in tripwires), case["name"]
        assert any(letter in body for letter in "çğıöşüÇĞİÖŞÜ"), case["name"]


# --- group 5: the edge log is not a PHI channel (invariant 6) ------------------------


def test_a_coraza_block_line_yields_an_event_with_no_free_text_at_all() -> None:
    """Coraza's own log line for a blocked request carries ``[data "Matched
    Data: … found within ARGS:json.text_tr: …"]`` and ``[uri "…?q=…"]`` — the
    patient's sentence and the query string, verbatim. Shipping that line is a
    PHI disclosure dressed as a security signal, so the edge ships a closed
    record instead: there is no field a sentence could occupy."""
    lines = CORAZA_LOG_FIXTURE.read_text(encoding="utf-8").splitlines()
    utterance = "Göğsümde şiddetli ağrı"
    leaking = [line for line in lines if utterance in line]
    assert leaking, "the fixture must contain a line that leaks, or it proves nothing"

    for line in leaking:
        event = parse_coraza_line(line)
        assert event is not None
        rendered = repr(event)
        assert utterance not in rendered
        assert "Matched Data" not in rendered
        for fragment in ("text_tr", "ARGS", "?", "&"):
            assert fragment not in rendered, fragment


def test_the_event_still_carries_the_signal_it_exists_to_carry() -> None:
    """The near-miss control on the redactor: a scrubber that drops everything
    is exactly as useful as one that drops nothing."""
    lines = CORAZA_LOG_FIXTURE.read_text(encoding="utf-8").splitlines()
    events = [event for event in map(parse_coraza_line, lines) if event is not None]
    assert events

    blocking = [event for event in events if event.blocked]
    assert blocking, "the fixture contains a block; the parser must see it"
    assert all(event.anomaly_score is not None for event in blocking)
    assert {event.rule_id for event in events} >= {942100, 949110}
    assert RuleClass.SQLI in {event.rule_class for event in events}
    assert all(len(event.unique_id) > 0 for event in events)


def test_an_unknown_line_is_dropped_rather_than_guessed() -> None:
    assert parse_coraza_line("2026-09-03T20:00:00Z INF Configuration loaded") is None
    assert parse_coraza_line("") is None


def test_the_event_type_has_no_field_a_body_could_occupy() -> None:
    fields = set(EdgeEvent.__dataclass_fields__)
    assert fields == {
        "rule_id",
        "rule_class",
        "severity",
        "crs_version",
        "anomaly_score",
        "unique_id",
        "blocked",
    }


# --- group 6: CrowdSec scenarios are on, and are not a PHI channel either ------------


def _rendered_scenarios() -> dict[str, dict[str, Any]]:
    documents: dict[str, dict[str, Any]] = {}
    for path in sorted(CROWDSEC_SCENARIO_DIR.glob("*.yaml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        documents[document["name"]] = document
    return documents


def test_the_policy_declares_scenarios_and_every_one_is_rendered() -> None:
    """One file per scenario, and the count has to match in both directions.

    CrowdSec's local inventory keys on the file, so three documents in one file
    load as one scenario and the other two are silently absent — a tier that
    reports "scenarios on" and runs a third of them. That is what booting it
    found (docs/evidence/INT-203.md §5).
    """
    policy = _policy()
    assert policy.crowdsec.scenarios, "no scenario is not 'scenarios on'"
    rendered = _rendered_scenarios()
    assert set(rendered) == {scenario.name for scenario in policy.crowdsec.scenarios}
    assert len(list(CROWDSEC_SCENARIO_DIR.glob("*.yaml"))) == len(policy.crowdsec.scenarios)
    for scenario in policy.crowdsec.scenarios:
        assert scenario.remediation is True, scenario.name
        assert rendered[scenario.name]["labels"]["remediation"] is True


def test_a_scenario_file_the_policy_no_longer_declares_is_an_orphan() -> None:
    """The delete direction: a renderer that only ever writes leaves CrowdSec
    running a bucket nobody approved."""
    render = _renderer()
    assert render.orphan_scenarios(_policy()) == []


def test_crowdsec_never_talks_to_the_central_api() -> None:
    """files/10 §1: a third-party reputation service receiving our client
    addresses is a transfer nobody consented to. The scenarios run; the
    telemetry does not."""
    assert _policy().crowdsec.online_api is False
    config = yaml.safe_load((CROWDSEC_DIR / "config.yaml").read_text(encoding="utf-8"))
    assert config["api"]["server"].get("online_client", {}) in ({}, None)


#: Fields that would carry a request path, a query string or a header value
#: into a CrowdSec bucket key — and therefore into every alert raised from it.
_PATH_SHAPED = ("RequestPath", "RequestAddr", "RequestLine", "RequestHeaders", "http_path")


def _executable_lines(path: Path) -> list[str]:
    """Comments are prose and may say the word "security"; the rules are not."""
    return [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def test_no_scenario_or_parser_reads_a_path_or_a_query() -> None:
    """The CrowdSec side of invariant 6. A bucket keyed on the request path
    puts ``/v1/patients/<id>`` into every alert it raises, and an alert is
    shipped to the SIEM."""
    for path in [CROWDSEC_PARSER, *sorted(CROWDSEC_SCENARIO_DIR.glob("*.yaml"))]:
        for line in _executable_lines(path):
            for token in _PATH_SHAPED:
                assert token not in line, (path.name, line)
    for scenario in _policy().crowdsec.scenarios:
        for token in _PATH_SHAPED:
            assert token not in scenario.filter
            assert token not in scenario.groupby


def test_the_parser_extracts_exactly_two_values_from_a_request() -> None:
    """The positive half: a parser that extracts nothing is also a parser no
    scenario can fire on. Two statics come from the request — the client
    address and the status — and the rest are constants."""
    parser = yaml.safe_load(CROWDSEC_PARSER.read_text(encoding="utf-8"))
    statics = parser["nodes"][0]["statics"]
    extracted = {static["meta"] for static in statics if "expression" in static}
    assert extracted == {"source_ip", "http_status"}


def test_a_scenario_that_groups_by_a_request_path_is_refused(tmp_path: Path) -> None:
    document = _raw_policy()
    document["crowdsec"]["scenarios"][0]["groupby"] = "evt.Meta.http_path"
    with pytest.raises(ValidationError):
        load_edge_policy(_write(tmp_path, document))


def test_the_traefik_access_log_carries_no_request_path() -> None:
    """The upstream of the same rule: what CrowdSec cannot read, Traefik must
    not write. Traefik's access log is opt-in per field."""
    static = yaml.safe_load(TRAEFIK_STATIC.read_text(encoding="utf-8"))
    fields = static["accessLog"]["fields"]
    assert fields["defaultMode"] == "drop"
    assert fields["headers"]["defaultMode"] == "drop"
    kept = {name for name, mode in fields["names"].items() if mode == "keep"}
    assert "ClientHost" in kept and "DownstreamStatus" in kept
    for name in ("RequestPath", "RequestAddr", "RequestLine", "ClientUsername"):
        assert name not in kept, name


# --- group 7: certificates are automated, in both deployment shapes ------------------


def test_the_acme_resolver_is_complete_enough_to_actually_issue() -> None:
    tls = _policy().tls
    static = yaml.safe_load(TRAEFIK_STATIC.read_text(encoding="utf-8"))
    resolver = static["certificatesResolvers"][tls.resolver]["acme"]
    assert resolver["caServer"] == tls.ca_server
    assert resolver["storage"] == tls.storage
    assert tls.challenge in resolver


def test_the_acme_account_email_is_supplied_from_outside_the_repository() -> None:
    """A generated file may not carry it (invariant 14), and a resolver
    without it cannot order — so the compose service passes it through with no
    default, and a tier started without one fails loudly rather than serving
    something untrusted quietly."""
    tls = _policy().tls
    static = yaml.safe_load(TRAEFIK_STATIC.read_text(encoding="utf-8"))
    resolver = static["certificatesResolvers"][tls.resolver]["acme"]
    assert "email" not in resolver, "an ACME account email is not a committed value"

    compose = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    environment = compose["services"]["traefik"]["environment"]
    assert tls.account_email_env in environment
    assert environment[tls.account_email_env].endswith(":-}"), "no default"


def test_the_staging_acme_directory_is_refused_for_the_served_policy(tmp_path: Path) -> None:
    """A resolver pointed at Let's Encrypt staging issues certificates no
    browser trusts, and every dashboard still shows 'certificate issued'."""
    document = _raw_policy()
    document["tls"]["ca_server"] = "https://acme-staging-v02.api.letsencrypt.org/directory"
    with pytest.raises(ValidationError):
        load_edge_policy(_write(tmp_path, document))


def test_renewal_leaves_room_for_a_failure_and_a_human() -> None:
    assert _policy().tls.renew_before_days >= 30


def _manifests(text: str) -> list[dict[str, Any]]:
    return [document for document in yaml.safe_load_all(text) if document]


def test_the_shipped_manifest_is_an_issuer_and_no_certificate() -> None:
    """The fail-closed half, and it is the state of the repository today: the
    policy names no domain, because no production hostname for this system
    exists. An empty ``dnsNames`` is refused by cert-manager at apply time, in
    a cluster, later — so the object is absent rather than present and broken.
    """
    tls = _policy().tls
    assert tls.domains == []
    documents = _manifests(CERT_MANAGER.read_text(encoding="utf-8"))
    assert [document["kind"] for document in documents] == ["ClusterIssuer"]
    assert documents[0]["spec"]["acme"]["server"] == tls.ca_server


def test_naming_a_domain_renders_a_certificate_that_matches_the_policy() -> None:
    """The other half, which the shipped policy cannot exercise. Rendering is
    a function, so the behaviour is decided here rather than waiting for a
    hostname somebody has yet to choose — and the same renewal window reaches
    both deployment shapes from the one policy, which is the drift that
    otherwise expires a certificate in exactly one of them."""
    render = _renderer()
    policy = _policy().model_copy(
        update={
            "tls": _policy().tls.model_copy(
                update={"domains": ["intake.example.com", "api.intake.example.com"]}
            )
        }
    )
    documents = _manifests(render.render_cert_manager(policy))
    kinds = [document["kind"] for document in documents]
    assert kinds == ["ClusterIssuer", "Certificate"]
    certificate = documents[1]
    assert certificate["spec"]["dnsNames"] == [
        "intake.example.com",
        "api.intake.example.com",
    ]
    assert certificate["spec"]["renewBefore"] == f"{policy.tls.renew_before_days * 24}h"
    assert certificate["spec"]["issuerRef"]["name"] == policy.tls.issuer_name

    static = yaml.safe_load(render.render_traefik_static(policy))
    assert static["certificatesResolvers"][policy.tls.resolver]["acme"]["caServer"] == (
        certificate and documents[0]["spec"]["acme"]["server"]
    )
    # And the redirect appears with the certificate, never before it.
    assert static["entryPoints"]["web"]["http"]["redirections"]["entryPoint"]["to"] == (
        "websecure"
    )


def _renderer() -> Any:
    import importlib.util

    spec = importlib.util.spec_from_file_location("render_edge_conf", RENDERER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_certificate_expiry_signal_is_catalogued() -> None:
    """files/10 §7 lists certificate-expiry countdowns among the signals; a
    signal with no catalogue row is a dashboard panel nobody can build."""
    catalog = yaml.safe_load((REPO / "observability" / "metrics_catalog.yaml").read_text("utf-8"))
    names = {metric["name"] for metric in catalog["metrics"]}
    assert "sec_cert_expiry_days" in names
    assert "sec_waf_blocks_total" in names


# --- group 8: the tier itself -------------------------------------------------------


def test_the_edge_compose_tier_is_profile_gated_and_pinned() -> None:
    compose = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    services = compose["services"]
    assert {"traefik", "crowdsec"} <= set(services)
    for name, service in services.items():
        image = service["image"]
        assert ":" in image and not image.endswith((":latest", ":edge")), (name, image)
        assert service["profiles"], name


def test_the_edge_never_reaches_the_phi_network_except_through_the_upstream() -> None:
    """The WAF terminates outside; only the router leg crosses into the
    application network, and the PHI network is not one of the edge's."""
    compose = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    assert compose["networks"]["edge"].get("internal") is not True
    for name, service in compose["services"].items():
        assert "phi" not in service.get("networks", []), name


def test_only_the_traefik_service_publishes_a_port_and_only_on_loopback() -> None:
    compose = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    for name, service in compose["services"].items():
        for published in service.get("ports", []):
            assert name == "traefik", name
            assert str(published).startswith("127.0.0.1:"), published
