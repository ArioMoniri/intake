"""INT-205 — Wazuh + Falco deployment, rules, and the console feed.

Acceptance, verbatim from docs/backlog/issues.yaml:
  "auth anomalies, k8s audit, container runtime alerts wired to Security module"

What this file can honestly pin, and what it cannot.

A running Wazuh stack is a manager, an indexer with a JVM heap, and a Falco
agent that needs a kernel driver on the host. files/05 sizes Wazuh alone at
"12 GB + a part-time SRE"; HB-I1 (free 80–100 GB of disk) and HB-I2 (raise
Docker's RAM allocation — the security and observability tiers alone need
22 GB) are both open against this host. The tier is therefore scripted at full
size and NOT shrunk to fit, and this file pins the half that is decidable
without booting anything:

- the compose tier is its own file, profile-gated, tag-pinned, loopback-bound
  and literal-free, so infra/docker-compose.dev.yml stays untouched;
- every image's licence is recorded in observability/registry.yaml from a raw
  LICENSE blob with its sha256 and the date it was read (invariant 19);
- the Wazuh ruleset, the Falco ruleset and ossec.conf parse, and every rule
  resolves to one of the three signals the acceptance names;
- no alert threshold and no retention window is invented anywhere in the tier;
- **and, adversarially: a monitor reads everything, so a Turkish symptom
  sentence planted in a log line, in a filename, in a rule description and in
  a container name does not survive into an alert payload** (invariant 6).

The ingest itself — a manager receiving real events — is exercised by
`make siem` on a host that meets the preflight. Nothing here claims it ran.
"""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml
from intake_platform.siem import (
    AlertRefused,
    AlertSource,
    ConsoleFeed,
    DeployBlocked,
    RetentionNotConfiguredError,
    Severity,
    SiemConfigError,
    Signal,
    host_preflight,
    load_console_feed,
    load_falco_ruleset,
    load_ossec_config,
    load_rule_catalogue,
    load_wazuh_ruleset,
    normalise_falco,
    normalise_wazuh,
    scrub_path,
)
from intake_platform.siem.cli import main as cli_main

REPO = Path(__file__).resolve().parents[2]
INFRA = REPO / "infra"
SEC = INFRA / "security"
WAZUH_DIR = SEC / "wazuh"
FALCO_DIR = SEC / "falco"
OSSEC_CONF = WAZUH_DIR / "ossec.conf"
WAZUH_RULES = WAZUH_DIR / "rules" / "intake_rules.xml"
FALCO_CONF = FALCO_DIR / "falco.yaml"
FALCO_RULES = FALCO_DIR / "rules" / "intake_rules.yaml"
COMPOSE_PATH = INFRA / "docker-compose.siem.yml"
UP_SCRIPT = REPO / "scripts" / "security" / "siem_up.sh"
SECRETS_SCRIPT = REPO / "scripts" / "security" / "siem_secrets.sh"
REGISTRY_PATH = REPO / "observability" / "registry.yaml"
SLO_PATH = REPO / "docs" / "slo" / "siem.yaml"
RUNBOOK = REPO / "docs" / "security" / "incident-runbook.md"

#: The planted adversary, borrowed from tests/observability/test_langfuse_gate.py
#: so the two PHI gates agree on what patient narrative looks like: B1 Turkish,
#: spaces, Turkish letters, no identifier to key off.
TURKISH_SYMPTOM = "Göğsümde iki gündür şiddetli bir ağrı var ve nefes almakta zorlanıyorum."

#: The same sentence shaped as a filename — no spaces, so a naive "reject
#: anything with a space" guard would let it through.
TURKISH_FILENAME = "Ayse-Yilmaz-göğüs-ağrısı-anamnez.txt"

#: A validated TC Kimlik number (the checksum matters: intake_platform.redaction
#: only masks numbers that pass it) inside an otherwise ASCII-safe path element.
TCKN_FILENAME = "hasta-10000000146-rapor.pdf"

#: Anything shaped like a credential in a committed file is invariant 14's
#: failure mode, whatever it is named.
SECRET_SHAPED = re.compile(
    r"(?:pass|passwd|password|secret|key|token)\s*[:=]\s*(?!\$|\{\{|\"\$|<|#)[^\s#]{6,}",
    re.IGNORECASE,
)

#: The three signals INT-205's acceptance names, and nothing else invented
#: alongside them.
ACCEPTANCE_SIGNALS = {Signal.AUTH_ANOMALY, Signal.K8S_AUDIT, Signal.CONTAINER_RUNTIME}


def _compose() -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    return loaded


def _registry_rows() -> dict[str, dict[str, Any]]:
    raw: dict[str, Any] = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    return {row["component"]: row for row in raw["components"]}


def _falco_event(**overrides: Any) -> dict[str, Any]:
    """A Falco JSON alert in the shape falco writes with json_output: true."""
    event = {
        "hostname": "intake-node-1",
        "output": "Terminal shell in container (user=root container_id=9f2b1c0d4e5a)",
        "priority": "Critical",
        "rule": "intake_shell_in_phi_container",
        "source": "syscall",
        "tags": ["container", "intake_container_runtime"],
        "time": "2026-08-29T09:14:02.123456789Z",
        "output_fields": {
            "container.id": "9f2b1c0d4e5a",
            "container.name": "intake-api",
            "evt.time": 1787051642123456789,
            "fd.name": "/usr/bin/bash",
            "proc.cmdline": "bash -i",
            "proc.pname": "containerd-shim",
            "user.name": "root",
        },
    }
    event.update(overrides)
    return event


def _wazuh_event(**overrides: Any) -> dict[str, Any]:
    """A Wazuh alert in the shape alerts.json carries."""
    event = {
        "timestamp": "2026-08-29T09:14:02.500+0000",
        "agent": {"id": "001", "name": "intake-api"},
        "manager": {"name": "wazuh-manager"},
        "id": "1787051642.884231",
        "full_log": '{"event": "sec.auth_failure", "principal_id": "p_9f2b"}',
        "rule": {
            "id": "100100",
            "level": 12,
            "description": "intake: repeated authentication failure for a principal",
            "groups": ["intake", "intake_auth_anomaly"],
        },
        "data": {"event": "sec.auth_failure", "principal_id": "p_9f2b"},
    }
    event.update(overrides)
    return event


# --- the compose tier -------------------------------------------------------------------


class TestSiemComposeTier:
    def test_it_is_its_own_file_and_the_shared_dev_tier_is_untouched(self) -> None:
        """INT-202 set the precedent and tests/infra pins it in both files:
        infra/docker-compose.dev.yml is the hottest shared file in the repo."""
        assert COMPOSE_PATH.is_file()
        dev = (INFRA / "docker-compose.dev.yml").read_text(encoding="utf-8")
        for name in ("wazuh", "falco", "siem"):
            assert name not in dev, f"{name} leaked into the shared dev tier"

    def test_every_service_is_gated_behind_the_siem_profile(self) -> None:
        for name, service in _compose()["services"].items():
            assert service.get("profiles") == ["siem"], (
                f"{name} would start with the plain dev tier"
            )

    def test_every_image_is_tag_pinned(self) -> None:
        for name, service in _compose()["services"].items():
            ref = str(service.get("image", ""))
            assert ref, f"{name} pulls no image"
            assert ":" in ref, f"{name}: unpinned image reference {ref}"
            assert ref.rsplit(":", 1)[1] not in {"latest", ""}, f"{name}: floating tag {ref}"

    def test_every_published_port_binds_loopback(self) -> None:
        for name, service in _compose()["services"].items():
            for published in service.get("ports", []):
                assert str(published).startswith("127.0.0.1:"), (
                    f"{name} publishes {published} on every interface"
                )

    def test_every_service_has_a_healthcheck(self) -> None:
        """Invariant 15. Nothing in this tier is a one-shot."""
        for name, service in _compose()["services"].items():
            assert "healthcheck" in service, f"{name} has no healthcheck"

    def test_no_credential_literal_anywhere_in_the_tier(self) -> None:
        for path in (COMPOSE_PATH, OSSEC_CONF, FALCO_CONF, WAZUH_RULES, FALCO_RULES, UP_SCRIPT):
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith(("#", "//", "<!--", "*")):
                    continue
                assert SECRET_SHAPED.search(line) is None, (
                    f"{path.name}:{lineno} carries a credential literal: {line!r}"
                )

    def test_secrets_interpolate_and_carry_no_inline_default(self) -> None:
        """Invariant 14: a `${X:-default}` on a secret is how a dev default
        reaches a deployed stack."""
        text = COMPOSE_PATH.read_text(encoding="utf-8")
        assert "${INDEXER_PASSWORD" in text
        for match in re.finditer(r"\$\{([A-Z0-9_]+):-", text):
            name = match.group(1)
            assert not any(token in name for token in ("PASSWORD", "SECRET", "TOKEN", "KEY")), (
                f"{name} has an inline default"
            )

    def test_there_is_no_second_console_into_the_alert_store(self) -> None:
        """files/08 §0b F1 / invariant 48: Grafana, Langfuse and Unleash reached
        directly rather than through the console is a parallel authorization
        plane. A Wazuh dashboard would be the same defect over security alerts,
        and files/10 §7 puts the dashboards in the console's Security module."""
        services = _compose()["services"]
        assert "wazuh-dashboard" not in services
        joined = " ".join(str(s.get("image", "")) for s in services.values())
        assert "dashboard" not in joined

    def test_the_manager_and_the_indexer_and_falco_are_all_present(self) -> None:
        """Not shrunk to fit the host: the tier that is scripted is the tier
        files/10 §7 names."""
        assert set(_compose()["services"]) == {"wazuh-manager", "wazuh-indexer", "falco"}

    def test_falco_reaches_the_manager_over_a_shared_volume_not_the_network(self) -> None:
        """Falco writes JSON events; the manager's logcollector reads them. No
        extra forwarder image, and no port between them."""
        compose = _compose()
        falco_mounts = {str(v).split(":")[1] for v in compose["services"]["falco"]["volumes"]}
        manager_mounts = {
            str(v).split(":")[1] for v in compose["services"]["wazuh-manager"]["volumes"]
        }
        assert "/var/log/falco" in falco_mounts & manager_mounts

    def test_every_bind_mount_source_exists(self) -> None:
        for name, service in _compose()["services"].items():
            for volume in service.get("volumes", []):
                source = str(volume).split(":", 1)[0]
                if not source.startswith("."):
                    continue
                assert (INFRA / source).exists(), f"{name} mounts a missing path: {source}"

    def test_no_vendor_telemetry_is_left_on(self) -> None:
        """files/08 §9: 'no vendor network'. Both products phone home by default."""
        text = COMPOSE_PATH.read_text(encoding="utf-8") + FALCO_CONF.read_text(encoding="utf-8")
        assert "INDEXER_TELEMETRY" not in text or "false" in text
        falco: dict[str, Any] = yaml.safe_load(FALCO_CONF.read_text(encoding="utf-8"))
        assert falco["webserver"]["prometheus_metrics_enabled"] is True
        assert falco["http_output"]["enabled"] is False
        assert falco["grpc_output"]["enabled"] is False


# --- licences: read from the raw blob, recorded with the date --------------------------


class TestLicences:
    def test_every_image_in_the_tier_has_a_registry_row(self) -> None:
        rows = _registry_rows()
        for component in ("wazuh-manager", "wazuh-indexer", "falco"):
            assert component in rows, f"{component} is not in observability/registry.yaml"

    def test_each_row_records_a_dated_hashed_licence_blob(self) -> None:
        """Invariant 19: verified from the raw LICENSE blob, never a badge."""
        rows = _registry_rows()
        for component in ("wazuh-manager", "wazuh-indexer", "falco"):
            row = rows[component]
            assert row.get("licence_verified_at") is not None, f"{component}: no date"
            assert str(row.get("licence_blob_url", "")).startswith("https://raw."), component
            assert re.fullmatch(r"[0-9a-f]{64}", str(row.get("licence_blob_sha256", ""))), (
                f"{component}: no sha256 for the blob that was read"
            )

    def test_wazuh_is_not_recorded_as_a_one_word_licence(self) -> None:
        """The Wazuh LICENSE is GPL-2.0-only plus an OpenSSL linking exception
        plus an extended derivative-work interpretation, and it says in terms
        that it covers decoders and rules as well as source. 'GPL-2.0' alone
        would be the laundered claim files/03 §4.9.0 rule 3 exists to catch."""
        row = _registry_rows()["wazuh-manager"]
        assert "GPL-2.0-only" in row["license"]
        note = str(row.get("licence_note", ""))
        assert "OpenSSL" in note
        assert "derivative" in note.lower()
        assert "decoders" in note and "rules" in note
        assert "redistribut" in note.lower(), (
            "the note must record that the extended clause binds only on redistribution"
        )

    def test_the_apache_rows_say_which_blob_and_how_many_lines(self) -> None:
        rows = _registry_rows()
        for component in ("wazuh-indexer", "falco"):
            assert "Apache-2.0" in rows[component]["license"]
            assert "blob" in str(rows[component]["license"]).lower()

    def test_phi_path_rows_are_self_hostable(self) -> None:
        rows = _registry_rows()
        for component in ("wazuh-manager", "wazuh-indexer", "falco"):
            row = rows[component]
            if row["phi_path"]:
                assert row["self_hostable"] is True

    def test_none_of_them_claims_to_be_running_here(self) -> None:
        """HB-I1 and HB-I2. A registry row that says `self_hosted_now: true`
        for a stack nobody has booted is a fiction the release gate believes."""
        rows = _registry_rows()
        for component in ("wazuh-manager", "wazuh-indexer", "falco"):
            assert rows[component]["self_hosted_now"] is False
            assert "HB-I1" in rows[component]["host"] or "HB-I2" in rows[component]["host"]


# --- the rules --------------------------------------------------------------------------


class TestWazuhRuleset:
    def test_the_shipped_ruleset_parses(self) -> None:
        ruleset = load_wazuh_ruleset(WAZUH_RULES)
        assert ruleset.rules

    def test_every_rule_id_is_in_the_user_range(self) -> None:
        """Wazuh reserves ids below 100000 for its own ruleset; colliding with
        them silently replaces a vendor rule."""
        for rule in load_wazuh_ruleset(WAZUH_RULES).rules:
            assert 100000 <= rule.rule_id < 120000, f"rule {rule.rule_id} is outside 100000-119999"

    def test_rule_ids_are_unique(self) -> None:
        ids = [rule.rule_id for rule in load_wazuh_ruleset(WAZUH_RULES).rules]
        assert len(ids) == len(set(ids))

    def test_every_rule_carries_one_of_the_three_acceptance_signals(self) -> None:
        for rule in load_wazuh_ruleset(WAZUH_RULES).rules:
            assert rule.signal in ACCEPTANCE_SIGNALS, f"rule {rule.rule_id}: {rule.signal}"

    def test_all_three_acceptance_signals_are_actually_covered(self) -> None:
        covered = {rule.signal for rule in load_wazuh_ruleset(WAZUH_RULES).rules}
        assert covered == ACCEPTANCE_SIGNALS

    def test_no_rule_invents_a_correlation_threshold(self) -> None:
        """files/10 §7 names the signals — failed logins and OTP anomalies per
        phone/IP/ASN, impossible travel, token reuse — and states no number for
        any of them. A `frequency`/`timeframe` pair would be a detection
        threshold nobody supplied."""
        text = WAZUH_RULES.read_text(encoding="utf-8")
        for banned in ("<frequency>", "<timeframe>", "<ignore>", "same_source_ip"):
            assert banned not in text, f"{banned} is an invented threshold"

    def test_no_rule_description_interpolates_an_event_field(self) -> None:
        """Wazuh expands `$(field)` inside a description. That is how patient
        text would reach a rule name, which is why the feed resolves names from
        this file by id and never from the alert."""
        assert "$(" not in WAZUH_RULES.read_text(encoding="utf-8")

    def test_a_rule_outside_the_user_range_is_refused(self, tmp_path: Path) -> None:
        body = WAZUH_RULES.read_text(encoding="utf-8").replace('id="100100"', 'id="5716"')
        path = tmp_path / "bad.xml"
        path.write_text(body, encoding="utf-8")
        with pytest.raises(SiemConfigError, match="user range"):
            load_wazuh_ruleset(path)

    def test_a_rule_with_an_unknown_group_is_refused(self, tmp_path: Path) -> None:
        body = WAZUH_RULES.read_text(encoding="utf-8").replace(
            "intake_auth_anomaly", "intake_something_else"
        )
        path = tmp_path / "bad.xml"
        path.write_text(body, encoding="utf-8")
        with pytest.raises(SiemConfigError, match="signal"):
            load_wazuh_ruleset(path)

    def test_a_frequency_attribute_is_refused_by_the_loader_too(self, tmp_path: Path) -> None:
        body = WAZUH_RULES.read_text(encoding="utf-8").replace(
            "</rule>", "<frequency>8</frequency></rule>", 1
        )
        path = tmp_path / "bad.xml"
        path.write_text(body, encoding="utf-8")
        with pytest.raises(SiemConfigError, match="threshold"):
            load_wazuh_ruleset(path)

    def test_a_malformed_file_is_refused_not_crashed(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.xml"
        path.write_text("<group>", encoding="utf-8")
        with pytest.raises(SiemConfigError):
            load_wazuh_ruleset(path)


class TestFalcoRuleset:
    def test_the_shipped_ruleset_parses(self) -> None:
        assert load_falco_ruleset(FALCO_RULES).rules

    def test_every_rule_is_container_runtime_and_carries_a_closed_priority(self) -> None:
        for rule in load_falco_ruleset(FALCO_RULES).rules:
            assert rule.signal is Signal.CONTAINER_RUNTIME
            assert rule.severity in set(Severity)

    def test_no_rule_output_carries_a_command_line_or_file_content(self) -> None:
        """Falco's stock outputs interpolate `proc.cmdline` and `evt.buffer`.
        Ours do not — and the feed drops them regardless, because a rules file
        is editable on the host and the boundary must not depend on it."""
        for rule in load_falco_ruleset(FALCO_RULES).rules:
            for banned in ("proc.cmdline", "evt.buffer", "evt.args", "fd.name"):
                assert banned not in rule.output, f"{rule.name} interpolates {banned}"

    def test_rule_names_are_unique(self) -> None:
        names = [rule.name for rule in load_falco_ruleset(FALCO_RULES).rules]
        assert len(names) == len(set(names))

    def test_a_rule_without_a_priority_is_refused(self, tmp_path: Path) -> None:
        raw: dict[str, Any] | list[Any] = yaml.safe_load(FALCO_RULES.read_text(encoding="utf-8"))
        assert isinstance(raw, list)
        entry = next(item for item in raw if "rule" in item)
        del entry["priority"]
        path = tmp_path / "bad.yaml"
        path.write_text(yaml.safe_dump(raw), encoding="utf-8")
        with pytest.raises(SiemConfigError, match="priority"):
            load_falco_ruleset(path)

    def test_an_unknown_priority_is_refused_not_coerced(self, tmp_path: Path) -> None:
        raw: list[Any] = yaml.safe_load(FALCO_RULES.read_text(encoding="utf-8"))
        entry = next(item for item in raw if "rule" in item)
        entry["priority"] = "Spicy"
        path = tmp_path / "bad.yaml"
        path.write_text(yaml.safe_dump(raw), encoding="utf-8")
        with pytest.raises(SiemConfigError, match="priority"):
            load_falco_ruleset(path)


class TestOssecConfig:
    def test_the_shipped_config_parses(self) -> None:
        assert load_ossec_config(OSSEC_CONF).localfiles

    def test_it_ingests_falco_events_the_k8s_audit_log_and_our_security_log(self) -> None:
        locations = {lf.location for lf in load_ossec_config(OSSEC_CONF).localfiles}
        assert "/var/log/falco/events.json" in locations
        assert "/var/log/kubernetes/audit.log" in locations
        assert "/var/log/intake/security.json" in locations

    def test_every_ingested_source_is_json_so_nothing_is_regex_scraped(self) -> None:
        for localfile in load_ossec_config(OSSEC_CONF).localfiles:
            assert localfile.log_format == "json", localfile.location

    def test_no_mail_relay_and_no_vendor_reporting(self) -> None:
        config = load_ossec_config(OSSEC_CONF)
        assert config.email_notification is False
        assert config.vendor_reporting is False

    def test_no_retention_or_rotation_window_is_invented(self) -> None:
        """files/06 §3's retention matrix has rows for audio, notes, tokens,
        audit, telemetry and 5651 traffic logs, and no row for SIEM alert
        storage. INT-212 owns the answer; until it lands the store expires
        nothing, which loses no evidence."""
        config = load_ossec_config(OSSEC_CONF)
        assert config.log_retention_days is None
        text = OSSEC_CONF.read_text(encoding="utf-8")
        assert "<rotation>" not in text
        assert "max_size" not in text

    def test_a_non_json_localfile_is_refused(self, tmp_path: Path) -> None:
        body = OSSEC_CONF.read_text(encoding="utf-8").replace(
            "<log_format>json</log_format>", "<log_format>syslog</log_format>", 1
        )
        path = tmp_path / "ossec.conf"
        path.write_text(body, encoding="utf-8")
        with pytest.raises(SiemConfigError, match="json"):
            load_ossec_config(path)

    def test_an_email_relay_is_refused(self, tmp_path: Path) -> None:
        body = OSSEC_CONF.read_text(encoding="utf-8").replace(
            "<email_notification>no</email_notification>",
            "<email_notification>yes</email_notification>",
            1,
        )
        path = tmp_path / "ossec.conf"
        path.write_text(body, encoding="utf-8")
        with pytest.raises(SiemConfigError, match="egress|mail|email"):
            load_ossec_config(path)


class TestRuleCatalogue:
    def test_it_is_built_from_the_two_shipped_rulesets(self) -> None:
        catalogue = load_rule_catalogue(WAZUH_RULES, FALCO_RULES)
        assert catalogue.wazuh_ids
        assert catalogue.falco_names

    def test_it_resolves_a_wazuh_id_to_a_name_and_a_signal(self) -> None:
        catalogue = load_rule_catalogue(WAZUH_RULES, FALCO_RULES)
        entry = catalogue.for_wazuh(100100)
        assert entry is not None
        assert entry.signal is Signal.AUTH_ANOMALY

    def test_an_unknown_id_resolves_to_nothing_rather_than_guessing(self) -> None:
        assert load_rule_catalogue(WAZUH_RULES, FALCO_RULES).for_wazuh(5716) is None


# --- path scrubbing ---------------------------------------------------------------------


class TestScrubPath:
    def test_an_ordinary_system_path_survives_whole(self) -> None:
        scrubbed = scrub_path("/usr/bin/bash")
        assert scrubbed.safe_prefix == "/usr/bin/bash"
        assert scrubbed.truncated is False
        assert scrubbed.digest is None

    def test_a_turkish_filename_is_truncated_at_the_component_that_carries_it(self) -> None:
        scrubbed = scrub_path(f"/data/uploads/{TURKISH_FILENAME}")
        assert scrubbed.safe_prefix == "/data/uploads"
        assert scrubbed.truncated is True
        assert scrubbed.digest is not None
        assert TURKISH_FILENAME not in scrubbed.safe_prefix

    def test_a_directory_carrying_patient_text_truncates_before_it(self) -> None:
        scrubbed = scrub_path(f"/data/{TURKISH_SYMPTOM}/rapor.txt")
        assert scrubbed.safe_prefix == "/data"
        assert scrubbed.truncated is True

    def test_an_identifier_inside_an_ascii_component_still_truncates(self) -> None:
        """intake_platform.redaction is reused rather than re-implemented: if
        redaction changes the component, the component is not safe to keep."""
        scrubbed = scrub_path(f"/var/lib/intake/{TCKN_FILENAME}")
        assert scrubbed.truncated is True
        assert "10000000146" not in scrubbed.safe_prefix

    def test_the_digest_is_stable_and_correlates_two_alerts_on_one_file(self) -> None:
        first = scrub_path(f"/data/uploads/{TURKISH_FILENAME}")
        second = scrub_path(f"/data/uploads/{TURKISH_FILENAME}")
        third = scrub_path("/data/uploads/other.txt")
        assert first.digest == second.digest
        assert first.digest != third.digest

    def test_depth_survives_because_it_is_a_number(self) -> None:
        assert scrub_path(f"/data/uploads/{TURKISH_FILENAME}").depth == 3

    def test_an_overlong_component_is_truncated_even_if_it_is_ascii(self) -> None:
        scrubbed = scrub_path("/var/log/" + "a" * 200)
        assert scrubbed.truncated is True

    def test_a_relative_path_is_still_scrubbed(self) -> None:
        assert scrub_path(f"./{TURKISH_FILENAME}").truncated is True

    def test_an_empty_path_is_refused(self) -> None:
        with pytest.raises(AlertRefused):
            scrub_path("")


# --- normalisation: the adversarial PHI proof -------------------------------------------


class TestFalcoNormalisation:
    def test_a_known_rule_normalises_to_an_alert(self) -> None:
        alert = normalise_falco(_falco_event(), load_rule_catalogue(WAZUH_RULES, FALCO_RULES))
        assert alert.source is AlertSource.FALCO
        assert alert.signal is Signal.CONTAINER_RUNTIME
        assert alert.rule_name == "intake_shell_in_phi_container"
        assert alert.container_id == "9f2b1c0d4e5a"

    def test_an_unknown_rule_is_admitted_with_a_reference_not_a_name(self) -> None:
        """A rule name that is not in a committed ruleset is not a name we can
        vouch for — Falco loads the stock rules too, and a rules file is
        editable on the host."""
        catalogue = load_rule_catalogue(WAZUH_RULES, FALCO_RULES)
        alert = normalise_falco(_falco_event(rule="Terminal shell in container"), catalogue)
        assert alert.rule_name is None
        assert re.fullmatch(r"[0-9a-f]{16}", alert.rule_ref)

    def test_the_priority_ladder_is_closed(self) -> None:
        catalogue = load_rule_catalogue(WAZUH_RULES, FALCO_RULES)
        with pytest.raises(AlertRefused, match="priority"):
            normalise_falco(_falco_event(priority="Spicy"), catalogue)

    @pytest.mark.parametrize(
        ("priority", "severity"),
        [
            ("Emergency", Severity.SEV1),
            ("Alert", Severity.SEV1),
            ("Critical", Severity.SEV2),
            ("Error", Severity.SEV2),
            ("Warning", Severity.SEV3),
            ("Notice", Severity.SEV3),
            ("Informational", Severity.SEV4),
            ("Debug", Severity.SEV4),
        ],
    )
    def test_every_falco_priority_lands_on_a_runbook_severity(
        self, priority: str, severity: Severity
    ) -> None:
        catalogue = load_rule_catalogue(WAZUH_RULES, FALCO_RULES)
        alert = normalise_falco(_falco_event(priority=priority), catalogue)
        assert alert.severity is severity


class TestWazuhNormalisation:
    def test_a_known_rule_normalises_to_an_alert(self) -> None:
        alert = normalise_wazuh(_wazuh_event(), load_rule_catalogue(WAZUH_RULES, FALCO_RULES))
        assert alert.source is AlertSource.WAZUH
        assert alert.signal is Signal.AUTH_ANOMALY
        assert alert.rule_ref == "100100"
        assert alert.agent_id == "001"

    def test_the_rule_name_comes_from_the_committed_file_not_the_event(self) -> None:
        catalogue = load_rule_catalogue(WAZUH_RULES, FALCO_RULES)
        event = _wazuh_event()
        event["rule"]["description"] = TURKISH_SYMPTOM
        alert = normalise_wazuh(event, catalogue)
        assert alert.rule_name is not None
        assert TURKISH_SYMPTOM not in alert.rule_name

    def test_a_stock_rule_is_admitted_with_an_id_and_no_name(self) -> None:
        catalogue = load_rule_catalogue(WAZUH_RULES, FALCO_RULES)
        event = _wazuh_event()
        event["rule"] = {"id": "5716", "level": 5, "description": "sshd: authentication failed"}
        alert = normalise_wazuh(event, catalogue)
        assert alert.rule_ref == "5716"
        assert alert.rule_name is None
        assert alert.signal is Signal.UNCLASSIFIED

    @pytest.mark.parametrize(
        ("level", "severity"),
        [
            (15, Severity.SEV1),
            (14, Severity.SEV2),
            (12, Severity.SEV2),
            (7, Severity.SEV3),
            (3, Severity.SEV4),
        ],
    )
    def test_the_wazuh_level_ladder_maps_onto_the_runbook_ladder(
        self, level: int, severity: Severity
    ) -> None:
        catalogue = load_rule_catalogue(WAZUH_RULES, FALCO_RULES)
        event = _wazuh_event()
        event["rule"] = {"id": "5716", "level": level, "description": "x"}
        assert normalise_wazuh(event, catalogue).severity is severity

    def test_a_level_outside_the_wazuh_scale_is_refused(self) -> None:
        catalogue = load_rule_catalogue(WAZUH_RULES, FALCO_RULES)
        event = _wazuh_event()
        event["rule"] = {"id": "5716", "level": 99, "description": "x"}
        with pytest.raises(AlertRefused, match="level"):
            normalise_wazuh(event, catalogue)


class TestNoPatientTextReachesAnAlert:
    """The adversarial half. A security monitor reads everything on the box,
    which makes the alert payload the single most likely place for PHI to
    escape (files/10 §9 incident-response: 'PHI pasted into tickets or chat
    during the response'). Every seam that could carry narrative is planted."""

    @staticmethod
    def _blob(alert: Any) -> str:
        return json.dumps(alert.model_dump(mode="json"), ensure_ascii=False)

    def test_a_symptom_sentence_in_a_falco_log_line_does_not_reach_the_alert(self) -> None:
        catalogue = load_rule_catalogue(WAZUH_RULES, FALCO_RULES)
        event = _falco_event(output=f"Suspicious write ({TURKISH_SYMPTOM})")
        blob = self._blob(normalise_falco(event, catalogue))
        assert TURKISH_SYMPTOM not in blob
        assert "ağrı" not in blob

    def test_a_symptom_sentence_in_a_falco_filename_does_not_reach_the_alert(self) -> None:
        catalogue = load_rule_catalogue(WAZUH_RULES, FALCO_RULES)
        event = _falco_event()
        event["output_fields"]["fd.name"] = f"/data/uploads/{TURKISH_FILENAME}"
        alert = normalise_falco(event, catalogue)
        blob = self._blob(alert)
        assert TURKISH_FILENAME not in blob
        assert "göğüs" not in blob
        assert alert.path is not None
        assert alert.path.truncated is True

    def test_a_symptom_sentence_in_a_command_line_does_not_reach_the_alert(self) -> None:
        catalogue = load_rule_catalogue(WAZUH_RULES, FALCO_RULES)
        event = _falco_event()
        event["output_fields"]["proc.cmdline"] = f"cat /tmp/{TURKISH_FILENAME}"
        assert TURKISH_FILENAME not in self._blob(normalise_falco(event, catalogue))

    def test_a_symptom_sentence_in_a_container_name_does_not_reach_the_alert(self) -> None:
        catalogue = load_rule_catalogue(WAZUH_RULES, FALCO_RULES)
        event = _falco_event()
        event["output_fields"]["container.name"] = TURKISH_SYMPTOM
        assert TURKISH_SYMPTOM not in self._blob(normalise_falco(event, catalogue))

    def test_a_symptom_sentence_in_a_hostname_does_not_reach_the_alert(self) -> None:
        catalogue = load_rule_catalogue(WAZUH_RULES, FALCO_RULES)
        assert TURKISH_SYMPTOM not in self._blob(
            normalise_falco(_falco_event(hostname=TURKISH_SYMPTOM), catalogue)
        )

    def test_a_symptom_sentence_in_the_wazuh_full_log_does_not_reach_the_alert(self) -> None:
        catalogue = load_rule_catalogue(WAZUH_RULES, FALCO_RULES)
        event = _wazuh_event(full_log=f'{{"transcript": "{TURKISH_SYMPTOM}"}}')
        assert TURKISH_SYMPTOM not in self._blob(normalise_wazuh(event, catalogue))

    def test_a_symptom_sentence_in_the_wazuh_data_block_does_not_reach_the_alert(self) -> None:
        catalogue = load_rule_catalogue(WAZUH_RULES, FALCO_RULES)
        event = _wazuh_event()
        event["data"] = {"event": "sec.auth_failure", "note": TURKISH_SYMPTOM}
        assert TURKISH_SYMPTOM not in self._blob(normalise_wazuh(event, catalogue))

    def test_a_symptom_sentence_in_a_syscheck_path_does_not_reach_the_alert(self) -> None:
        catalogue = load_rule_catalogue(WAZUH_RULES, FALCO_RULES)
        event = _wazuh_event()
        event["syscheck"] = {"path": f"/data/uploads/{TURKISH_FILENAME}"}
        blob = self._blob(normalise_wazuh(event, catalogue))
        assert TURKISH_FILENAME not in blob
        assert "ağrısı" not in blob

    def test_the_whole_event_is_planted_and_nothing_survives(self) -> None:
        """Belt and braces: every string in a Falco event replaced by the
        sentence. Whatever the normaliser reads, it cannot be this."""
        catalogue = load_rule_catalogue(WAZUH_RULES, FALCO_RULES)
        event = _falco_event()
        event["output_fields"] = {k: TURKISH_SYMPTOM for k in event["output_fields"]}
        event["output"] = TURKISH_SYMPTOM
        event["hostname"] = TURKISH_SYMPTOM
        alert = normalise_falco(event, catalogue)
        assert TURKISH_SYMPTOM not in self._blob(alert)

    def test_the_alert_model_itself_refuses_narrative_in_any_string_field(self) -> None:
        """The type is the guarantee, not the normaliser's diligence: a future
        caller constructing a SecurityAlert directly hits the same wall."""
        from intake_platform.siem import SecurityAlert

        with pytest.raises(ValueError, match="narrative|free text|not an identifier"):
            SecurityAlert(
                alert_id="a1",
                source=AlertSource.FALCO,
                rule_ref="0123456789abcdef",
                rule_name=TURKISH_SYMPTOM,
                signal=Signal.CONTAINER_RUNTIME,
                severity=Severity.SEV3,
                observed_at="2026-08-29T09:14:02Z",
                host_id="intake-node-1",
                container_id=None,
                agent_id=None,
                path=None,
            )

    def test_the_alert_has_no_field_a_request_body_could_occupy(self) -> None:
        from intake_platform.siem import SecurityAlert

        fields = set(SecurityAlert.model_fields)
        for forbidden in (
            "body",
            "full_log",
            "output",
            "message",
            "cmdline",
            "payload",
            "content",
            "transcript",
            "request",
        ):
            assert forbidden not in fields, f"SecurityAlert grew a {forbidden} field"

    def test_an_alert_never_carries_a_username(self) -> None:
        """`user.name` and `srcuser` are the two fields a Wazuh/Falco alert
        normally leads with, and a patient-facing kiosk account name is a
        personal identifier (invariant 6 — use ids, redact)."""
        from intake_platform.siem import SecurityAlert

        assert not {"user", "username", "user_name", "srcuser"} & set(SecurityAlert.model_fields)


# --- the console feed --------------------------------------------------------------------


class TestConsoleFeed:
    def _write(self, tmp_path: Path, events: list[dict[str, Any]]) -> Path:
        path = tmp_path / "alerts.json"
        path.write_text(
            "\n".join(json.dumps(event, ensure_ascii=False) for event in events) + "\n",
            encoding="utf-8",
        )
        return path

    def test_a_missing_stream_reads_as_unconfigured_not_as_an_empty_feed(
        self, tmp_path: Path
    ) -> None:
        """taxonomy_feed's fail-closed shape: None, never []. An empty Security
        module that means 'nothing detected' and an empty one that means 'the
        SIEM is not wired' must not look the same."""
        assert load_console_feed(tmp_path / "absent.json") is None

    def test_it_normalises_both_sources_into_one_ordered_feed(self, tmp_path: Path) -> None:
        path = self._write(tmp_path, [_falco_event(), _wazuh_event()])
        feed = load_console_feed(path)
        assert isinstance(feed, ConsoleFeed)
        assert len(feed.alerts) == 2
        assert {alert.source for alert in feed.alerts} == {AlertSource.FALCO, AlertSource.WAZUH}

    def test_it_carries_a_content_hash_so_the_console_can_cache(self, tmp_path: Path) -> None:
        path = self._write(tmp_path, [_falco_event()])
        feed = load_console_feed(path)
        assert feed is not None
        assert re.fullmatch(r"[0-9a-f]{64}", feed.version)

    def test_counts_are_by_signal_and_severity_which_is_what_the_module_renders(
        self, tmp_path: Path
    ) -> None:
        path = self._write(tmp_path, [_falco_event(), _wazuh_event()])
        feed = load_console_feed(path)
        assert feed is not None
        assert feed.counts.by_signal[Signal.CONTAINER_RUNTIME] == 1
        assert feed.counts.by_signal[Signal.AUTH_ANOMALY] == 1
        assert sum(feed.counts.by_severity.values()) == 2

    def test_a_refused_alert_is_counted_and_does_not_stop_the_feed(self, tmp_path: Path) -> None:
        path = self._write(tmp_path, [_falco_event(priority="Spicy"), _wazuh_event()])
        feed = load_console_feed(path)
        assert feed is not None
        assert len(feed.alerts) == 1
        assert feed.counts.refused == 1

    def test_an_unparseable_line_is_counted_not_raised(self, tmp_path: Path) -> None:
        path = tmp_path / "alerts.json"
        path.write_text("{not json\n" + json.dumps(_falco_event()) + "\n", encoding="utf-8")
        feed = load_console_feed(path)
        assert feed is not None
        assert feed.counts.refused == 1
        assert len(feed.alerts) == 1

    def test_no_patient_text_survives_a_whole_feed(self, tmp_path: Path) -> None:
        planted = _falco_event(output=TURKISH_SYMPTOM)
        planted["output_fields"]["fd.name"] = f"/data/{TURKISH_FILENAME}"
        wazuh = _wazuh_event(full_log=TURKISH_SYMPTOM)
        path = self._write(tmp_path, [planted, wazuh])
        feed = load_console_feed(path)
        assert feed is not None
        blob = json.dumps(feed.model_dump(mode="json"), ensure_ascii=False)
        for fragment in (TURKISH_SYMPTOM, TURKISH_FILENAME, "ağrı", "göğüs"):
            assert fragment not in blob


# --- the deployment: host preflight, retention, entry points -----------------------------


class TestHostPreflight:
    def test_this_host_is_blocked_and_says_which_rows_unblock_it(self) -> None:
        """Not a skip and not a shrunken stack: a typed refusal naming the open
        blockers. HB-I1 is disk, HB-I2 is Docker memory."""
        outcome = host_preflight(free_disk_bytes=19 * 1024**3, docker_memory_bytes=15 * 1024**3)
        assert isinstance(outcome, DeployBlocked)
        assert "HB-I1" in outcome.reason
        assert "HB-I2" in outcome.reason

    def test_a_host_that_meets_both_bounds_is_not_blocked(self) -> None:
        assert (
            host_preflight(free_disk_bytes=200 * 1024**3, docker_memory_bytes=32 * 1024**3) is None
        )

    def test_disk_alone_blocks_and_names_only_disk(self) -> None:
        outcome = host_preflight(free_disk_bytes=19 * 1024**3, docker_memory_bytes=32 * 1024**3)
        assert isinstance(outcome, DeployBlocked)
        assert "HB-I1" in outcome.reason
        assert "HB-I2" not in outcome.reason

    def test_memory_alone_blocks_and_names_only_memory(self) -> None:
        outcome = host_preflight(free_disk_bytes=200 * 1024**3, docker_memory_bytes=15 * 1024**3)
        assert isinstance(outcome, DeployBlocked)
        assert "HB-I2" in outcome.reason
        assert "HB-I1" not in outcome.reason

    def test_an_unreported_memory_allocation_says_so_rather_than_claiming_zero(self) -> None:
        """The CLI defaults to 0 when nobody passed a figure, and "0 GiB
        allocated" reads as a fact about the host rather than as the absence of
        one. A refusal that misdescribes the host is a refusal someone argues
        with instead of acting on."""
        outcome = host_preflight(free_disk_bytes=200 * 1024**3, docker_memory_bytes=0)
        assert isinstance(outcome, DeployBlocked)
        assert "not reported" in outcome.reason
        assert "0 GiB allocated" not in outcome.reason

    def test_the_memory_bound_is_the_one_the_blocker_states(self) -> None:
        """HB-I2: 'the security + observability tiers alone need 22 GB'. The
        bound is read out of the blocker, not chosen."""
        text = (REPO / "files" / "HUMAN_BLOCKERS.md").read_text(encoding="utf-8")
        row = next(line for line in text.splitlines() if "HB-I2" in line)
        assert "22 GB" in row


class TestRetentionIsRefusedNotInvented:
    def test_planning_a_deploy_without_a_retention_window_fails_closed(self) -> None:
        with pytest.raises(RetentionNotConfiguredError) as excinfo:
            cli_main(["--retention-days", "0"], env={})
        assert "INT-212" in str(excinfo.value)

    def test_no_default_retention_exists_anywhere_in_the_tier(self) -> None:
        for path in (COMPOSE_PATH, OSSEC_CONF, FALCO_CONF, UP_SCRIPT):
            text = path.read_text(encoding="utf-8")
            assert "INTAKE_SIEM_RETENTION_DAYS:-" not in text
            assert "INTAKE_SIEM_RETENTION_DAYS=-" not in text


class TestEntryPoints:
    def test_the_up_script_exists_and_is_executable(self) -> None:
        assert UP_SCRIPT.is_file()
        assert UP_SCRIPT.stat().st_mode & stat.S_IXUSR
        assert SECRETS_SCRIPT.is_file()
        assert SECRETS_SCRIPT.stat().st_mode & stat.S_IXUSR

    def test_both_scripts_are_strict_bash(self) -> None:
        for path in (UP_SCRIPT, SECRETS_SCRIPT):
            text = path.read_text(encoding="utf-8")
            assert text.startswith("#!/usr/bin/env bash")
            assert "set -euo pipefail" in text

    def test_the_dry_run_path_runs_here_and_exits_zero(self) -> None:
        proc = subprocess.run(  # noqa: S603
            [str(UP_SCRIPT), "--dry-run"],
            capture_output=True,
            text=True,
            cwd=REPO,
            env={**os.environ, "INTAKE_SIEM_RETENTION_DAYS": "90"},
            check=False,
        )
        assert proc.returncode == 0, proc.stderr
        assert "INT-205" in proc.stdout

    def test_the_dry_run_touches_no_container_runtime(self) -> None:
        body = UP_SCRIPT.read_text(encoding="utf-8").split("run_up()", 1)
        assert len(body) == 2, "the script must separate planning from execution"
        assert "docker" not in body[0], "the dry-run half reaches a container runtime"

    def test_the_real_run_refuses_on_this_host_and_names_the_blockers(self) -> None:
        proc = subprocess.run(  # noqa: S603
            [str(UP_SCRIPT), "--run"],
            capture_output=True,
            text=True,
            cwd=REPO,
            env={**os.environ, "INTAKE_SIEM_RETENTION_DAYS": "90"},
            check=False,
        )
        assert proc.returncode != 0
        combined = proc.stdout + proc.stderr
        assert "HB-I1" in combined or "HB-I2" in combined

    def test_the_real_run_refuses_without_a_retention_window(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "INTAKE_SIEM_RETENTION_DAYS"}
        proc = subprocess.run(  # noqa: S603
            [str(UP_SCRIPT), "--run"],
            capture_output=True,
            text=True,
            cwd=REPO,
            env=env,
            check=False,
        )
        assert proc.returncode != 0
        assert "INT-212" in (proc.stdout + proc.stderr)

    def test_make_carries_the_entry_points(self) -> None:
        makefile = (REPO / "Makefile").read_text(encoding="utf-8")
        for target in ("siem-config-check:", "siem-dry:", "siem:", "siem-down:", "siem-seed:"):
            assert re.search(rf"^{re.escape(target)}", makefile, re.M), f"no {target} target"

    def test_env_example_documents_the_knobs_without_adding_a_key(self) -> None:
        """tests/security/test_openbao_wiring.py allows exactly seven
        uncommented keys. SIEM knobs are documented, never assigned."""
        env = (REPO / "env.example").read_text(encoding="utf-8")
        assert "INDEXER_PASSWORD" in env
        assert "INTAKE_SIEM_RETENTION_DAYS" in env
        keys = {
            line.split("=", 1)[0]
            for line in env.splitlines()
            if "=" in line and not line.startswith("#")
        }
        assert "INDEXER_PASSWORD" not in keys
        assert "INTAKE_SIEM_RETENTION_DAYS" not in keys

    def test_the_secrets_script_names_exactly_what_the_compose_file_interpolates(self) -> None:
        text = SECRETS_SCRIPT.read_text(encoding="utf-8")
        compose = COMPOSE_PATH.read_text(encoding="utf-8")
        for name in re.findall(r"\$\{([A-Z0-9_]+)\}", compose):
            assert name in text, f"{name} is interpolated but never sourced from OpenBao"

    def test_the_runbook_points_at_what_actually_landed(self) -> None:
        text = RUNBOOK.read_text(encoding="utf-8")
        assert "infra/docker-compose.siem.yml" in text


class TestPlanCli:
    def test_it_renders_the_plan_and_reports_a_blocked_host(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = cli_main(
            ["--free-disk-bytes", str(19 * 1024**3)],
            env={"INTAKE_SIEM_RETENTION_DAYS": "90"},
        )
        out = capsys.readouterr().out
        assert code == 0, "a dry render is not a failure, whatever the host looks like"
        assert "BLOCKED" in out and "HB-I1" in out

    def test_enforce_host_turns_the_verdict_into_an_exit_code(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = cli_main(
            ["--free-disk-bytes", str(19 * 1024**3), "--enforce-host"],
            env={"INTAKE_SIEM_RETENTION_DAYS": "90"},
        )
        capsys.readouterr()
        assert code == 3

    def test_a_ready_host_renders_and_exits_zero(self, capsys: pytest.CaptureFixture[str]) -> None:
        code = cli_main(
            [
                "--free-disk-bytes",
                str(500 * 1024**3),
                "--container-memory-bytes",
                str(64 * 1024**3),
                "--enforce-host",
            ],
            env={"INTAKE_SIEM_RETENTION_DAYS": "90"},
        )
        out = capsys.readouterr().out
        assert code == 0
        assert "host              ready" in out

    def test_it_refuses_without_retention(self, capsys: pytest.CaptureFixture[str]) -> None:
        code = cli_main([], env={})
        assert code == 2
        assert "INT-212" in capsys.readouterr().out

    def test_a_non_numeric_retention_is_refused_not_coerced(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = cli_main([], env={"INTAKE_SIEM_RETENTION_DAYS": "forever"})
        assert code == 2
        capsys.readouterr()

    def test_it_reads_the_process_environment_when_none_is_passed(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("INTAKE_SIEM_RETENTION_DAYS", "45")
        code = cli_main([])
        assert code == 0
        assert "45" in capsys.readouterr().out

    def test_the_module_entry_point_is_the_same_cli(self) -> None:
        import intake_platform.siem.__main__ as entry

        assert entry.main is cli_main


# --- the monitoring contract (invariant 15) ----------------------------------------------


class TestMonitoringContract:
    def test_the_tier_declares_an_slo_on_the_boundary_we_own(self) -> None:
        """Wazuh's and Falco's liveness are probes, not error budgets. What we
        own is the scrub boundary, so that is what carries the objective —
        the same reasoning docs/slo/langfuse.yaml records."""
        from intake_platform.slo import load_slo_file

        slo_file = load_slo_file(SLO_PATH)
        assert slo_file.service == "siem"
        assert [slo.name for slo in slo_file.slos] == ["alert_scrub"]

    def test_the_sli_reads_the_catalogued_scrub_counters(self) -> None:
        from intake_platform.slo import load_slo_file, metric_references

        referenced = set()
        for slo in load_slo_file(SLO_PATH).slos:
            referenced |= metric_references(slo.sli)
        assert referenced == {"siem_alerts_ingested_total", "siem_alerts_refused_total"}

    def test_the_emitted_families_are_catalogued(self) -> None:
        from intake_platform.slo import load_metrics_catalog

        catalog = load_metrics_catalog(REPO / "observability" / "metrics_catalog.yaml")
        for name in (
            "siem_alerts_ingested_total",
            "siem_alerts_refused_total",
            "siem_alert_fields_dropped_total",
        ):
            assert name in catalog.names, f"{name} is not in the metrics catalogue"

    def test_each_component_declares_a_probe_the_runner_implements(self) -> None:
        from intake_probes.registry import ProbeId

        rows = _registry_rows()
        for component in ("wazuh-manager", "wazuh-indexer", "falco"):
            assert rows[component]["probe"] in set(ProbeId)

    def test_falco_exposes_a_health_endpoint_the_probe_can_reach(self) -> None:
        falco: dict[str, Any] = yaml.safe_load(FALCO_CONF.read_text(encoding="utf-8"))
        assert falco["webserver"]["enabled"] is True
        assert falco["webserver"]["listen_port"] == 8765


def test_the_sec_row_this_issue_belongs_to_exists_in_the_threat_model() -> None:
    """Invariant 16: every feature PR links its row in files/10 §9."""
    text = (REPO / "docs" / "security" / "threat-model.md").read_text(encoding="utf-8")
    assert "## `incident-response`" in text
