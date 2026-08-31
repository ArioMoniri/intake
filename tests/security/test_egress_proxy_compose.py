"""INT-018 — the dev forward proxy: compose service + generated squid.conf.

Acceptance clause under test, verbatim:
  "forward proxy in dev compose; only allow-listed vendor hosts reachable
   from PHI-path services; every egress logged {host,purpose,bytes,ts}
   feeding the vendor-transfer register; denial emits sec.egress_denied"

**Nothing here boots a container.** There is no Docker daemon in the session
this landed in, so the proxy is written and validated *statically* — the same
way INT-202 landed the backup tier (tests/infra/test_restore_drill.py). What
is decidable without a daemon is decided here:

- the compose service exists in the **default** dev tier (``make dev`` runs
  ``docker compose --profile clamav up -d --wait`` with no service list, so a
  non-profiled service starts with it), binds loopback only, is pinned by an
  exact tag **and** a digest (invariant 14 — a floating proxy tag on the PHI
  egress path is a supply-chain hole), carries a healthcheck, mounts exactly
  its config read-only, and carries no credential literal;
- ``infra/security/squid/squid.conf`` is **byte-identical** to what
  :func:`intake_platform.egress_proxy.render_squid_conf` produces from
  ``infra/security/egress-allowlist.yaml``. The proxy and the in-process
  policy therefore cannot drift: they are one source of truth, rendered
  twice. Hand-editing the conf fails this file;
- the rendered policy is default-deny, CONNECT-only, and matches the
  library's glob semantics exactly (``*.hf.co`` covers a subdomain and never
  the apex — the near-miss negative control);
- the access-log format carries {ts, host, port, decision, bytes_out} and
  **no** request path or query code (invariant 6). ``%>rd``/``%>rP`` are host
  and port; ``%ru``/``%rp`` and their variants are the path-bearing codes and
  must never appear;
- the PHI-path tier renders to a conf with **no reachable host at all**
  (invariant 19 / 00_STATE D11), including no vendor LLM domain.

The service is called ``forward-proxy`` rather than ``egress-proxy`` on
purpose: ``tests/voice/test_audio_retention_guard.py`` asserts that no dev
compose service name or image contains "egress"/"ingress"/"recorder", because
those are the LiveKit *recording* components (invariant 3). That guard is
correct and this file keeps it green rather than weakening it.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml
from intake_platform.egress import VENDOR_LLM_DOMAINS, EgressAllowlist, load_allowlist
from intake_platform.egress_proxy import (
    PROXY_PORT,
    SQUID_CONF_PATH,
    main,
    render_squid_conf,
)

REPO = Path(__file__).resolve().parents[2]
INFRA = REPO / "infra"
COMPOSE_PATH = INFRA / "docker-compose.dev.yml"
ALLOWLIST_PATH = INFRA / "security" / "egress-allowlist.yaml"

SERVICE = "forward-proxy"

#: Verified to exist as a multi-arch (amd64/arm64/ppc64le/s390x) manifest list
#: on Docker Hub on 31 Aug 2026 via the registry API. The digest is the
#: manifest-list digest for that tag.
EXPECTED_IMAGE = (
    "ubuntu/squid:6.6-24.04_edge@sha256:"
    "8a3baed477e2c282ab8aa5edad442f69873246964f225c5c2ae8364b6610963c"
)

#: Squid logformat codes that carry a URL path or query string. A transfer
#: record is {host, port, decision, bytes, ts} and nothing else (invariant 6):
#: a query string is exactly where a TC Kimlik would leak.
PATH_BEARING_CODES = ("%ru", "%>ru", "%<ru", "%rp", "%>rp", "%<rp", "%{Referer}")


def _compose() -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    return loaded


def _services() -> dict[str, dict[str, Any]]:
    services: dict[str, dict[str, Any]] = _compose()["services"]
    return services


def _service() -> dict[str, Any]:
    services = _services()
    assert SERVICE in services, (
        "INT-018's first acceptance words are 'forward proxy in dev compose' — "
        f"{COMPOSE_PATH.name} has no {SERVICE!r} service"
    )
    return services[SERVICE]


def _conf() -> str:
    return SQUID_CONF_PATH.read_text(encoding="utf-8")


def _allowlist() -> EgressAllowlist:
    return load_allowlist(ALLOWLIST_PATH)


# --- the compose service ----------------------------------------------------------


class TestComposeService:
    def test_forward_proxy_is_in_the_default_dev_tier(self) -> None:
        # `make dev` is `docker compose --profile clamav up -d --wait` with no
        # service list, so anything unprofiled starts with it. A proxy behind
        # a profile is a proxy nobody runs, and an enforcement point nobody
        # runs is not an enforcement point.
        assert "profiles" not in _service(), (
            "the forward proxy must start with `make dev`, not behind an opt-in profile"
        )

    def test_image_is_pinned_by_exact_tag_and_digest(self) -> None:
        image = str(_service()["image"])
        assert image == EXPECTED_IMAGE, image
        repository, _, rest = image.partition(":")
        assert repository == "ubuntu/squid"
        tag, _, digest = rest.partition("@")
        assert tag not in {"latest", "edge", ""}, f"floating tag: {image}"
        assert digest.startswith("sha256:") and len(digest) == len("sha256:") + 64, (
            "invariant 14 pins images: a proxy on the PHI egress path pinned only by a "
            "mutable tag is a supply-chain hole"
        )

    def test_published_ports_bind_loopback_only(self) -> None:
        ports = [str(port) for port in _service()["ports"]]
        assert ports, "the proxy publishes its listener for host-side services"
        for port in ports:
            assert port.startswith("127.0.0.1:"), f"forward proxy publishes {port}"
            assert port.endswith(f":{PROXY_PORT}"), port

    def test_has_a_healthcheck(self) -> None:
        healthcheck = _service().get("healthcheck")
        assert healthcheck and healthcheck.get("test")

    def test_mounts_exactly_its_config_read_only(self) -> None:
        volumes = [str(volume) for volume in _service().get("volumes", [])]
        assert len(volumes) == 1, "exactly the config file — the proxy stores nothing"
        source, target, mode = volumes[0].split(":")
        assert mode == "ro"
        assert target == "/etc/squid/squid.conf"
        assert source.startswith("./")
        assert (INFRA / source[2:]) == SQUID_CONF_PATH
        assert SQUID_CONF_PATH.exists()

    def test_carries_no_credential_literal(self) -> None:
        # invariant 14: secrets only from OpenBao. The proxy authenticates
        # nobody — access control is the ACL plus network placement — so there
        # is no credential to leak in the first place.
        service = _service()
        rendered = yaml.safe_dump(service)
        for marker in ("password", "passwd", "secret", "token", "api_key", "apikey"):
            assert marker not in rendered.lower(), f"{marker!r} appears in the proxy service"
        assert "environment" not in service or not service["environment"]

    def test_service_name_and_image_keep_the_recording_guard_green(self) -> None:
        # tests/voice/test_audio_retention_guard.py refuses a dev compose
        # service whose name or image contains egress/ingress/recorder — those
        # are LiveKit's recording components (invariant 3). This proxy is
        # named for what it is without colliding with that guard.
        haystack = f"{SERVICE} {_service()['image']}".lower()
        for token in ("egress", "ingress", "recorder"):
            assert token not in haystack

    def test_the_rest_of_the_dev_tier_is_untouched(self) -> None:
        # infra/docker-compose.dev.yml is the hottest shared file in the repo.
        expected = {
            "postgres",
            "redis",
            "hapi",
            "minio",
            "openbao",
            "clamav",
            "livekit",
            "ehrbase-db",
            "ehrbase",
            SERVICE,
        }
        assert set(_services()) == expected


# --- the generated squid.conf -----------------------------------------------------


class TestGeneratedConf:
    def test_committed_conf_is_byte_identical_to_the_render(self) -> None:
        # One source of truth, rendered twice: the in-process policy and the
        # proxy read the same allow-list. Hand-editing the conf fails here.
        assert _conf() == render_squid_conf(_allowlist(), tier="dev")

    def test_conf_says_it_is_generated_and_names_its_source(self) -> None:
        conf = _conf()
        assert "GENERATED" in conf
        assert "egress-allowlist.yaml" in conf

    def test_default_deny_is_the_last_word(self) -> None:
        rules = [line for line in _conf().splitlines() if line.startswith("http_access ")]
        assert rules[-1] == "http_access deny all"

    def test_only_connect_to_an_allow_listed_host_and_port_is_permitted(self) -> None:
        allows = [line for line in _conf().splitlines() if line.startswith("http_access allow")]
        assert allows, "the dev tier has hosts; none of them is reachable"
        for line in allows:
            assert " CONNECT " in f" {line} ", line
            assert " intake_clients " in f" {line} ", line
            assert re.search(r"\bport_\d+\b", line), line

    def test_every_dev_allow_list_entry_is_reachable_and_nothing_else_is(self) -> None:
        conf = _conf()
        dev = _allowlist().tiers.dev
        acl_hosts = set(re.findall(r"^acl vendor_\w+ dstdomain (\S+)$", conf, re.MULTILINE))
        acl_globs = set(re.findall(r"^acl vendor_\w+ dstdom_regex -i (\S+)$", conf, re.MULTILINE))
        assert acl_hosts == {entry.host for entry in dev if not entry.glob}
        # the glob rows are rendered as anchored regexes, one per entry
        assert len(acl_globs) == len([entry for entry in dev if entry.glob])

    def test_glob_regex_matches_a_subdomain_and_never_the_apex(self) -> None:
        # the near-miss negative control, at the proxy tier this time:
        # `*.hf.co` covers cdn-lfs-us-1.hf.co, never hf.co and never evilhf.co.
        patterns = re.findall(r"^acl vendor_\w+ dstdom_regex -i (\S+)$", _conf(), re.MULTILINE)
        assert patterns, "the shipped allow-list has a glob row; the render dropped it"
        for pattern in patterns:
            compiled = re.compile(pattern, re.IGNORECASE)
            suffix = pattern.rstrip("$").replace("^.+", "").replace("\\", "")
            assert compiled.search("cdn-lfs-us-1" + suffix)
            assert not compiled.search(suffix.lstrip("."))
            assert not compiled.search("evil" + suffix.lstrip("."))

    def test_ip_literal_and_metadata_destinations_are_denied(self) -> None:
        conf = _conf()
        assert "http_access deny to_localhost" in conf
        assert "http_access deny to_linklocal" in conf
        # dstdomain/dstdom_regex never match a bare IP, so an IP destination
        # falls through every allow rule to `deny all` — but say it anyway.

    def test_no_vendor_llm_domain_is_reachable_through_the_proxy(self) -> None:
        # invariant 19: the anthropic|openai|google adapters are the mock/dev
        # path only, blocked on the PHI path by this allow-list.
        conf = _conf()
        for domain in VENDOR_LLM_DOMAINS:
            assert domain not in conf, f"{domain} is reachable through the dev proxy"

    def test_phi_path_tier_renders_a_conf_that_reaches_nothing(self) -> None:
        rendered = render_squid_conf(_allowlist(), tier="phi_path")
        assert "http_access allow" not in rendered
        assert rendered.splitlines()[-1] == "http_access deny all"

    def test_conf_carries_no_credential_material(self) -> None:
        conf = _conf().lower()
        for marker in ("auth_param", "password", "basic_auth", "ncsa_auth", "proxy_auth"):
            assert marker not in conf, f"{marker!r} in squid.conf (invariant 14)"

    def test_proxy_stores_nothing(self) -> None:
        conf = _conf()
        assert "cache deny all" in conf
        assert "cache_dir" not in conf, "a caching egress proxy is a store of response bodies"

    def test_client_identity_is_not_forwarded(self) -> None:
        conf = _conf()
        assert "forwarded_for delete" in conf
        assert "via off" in conf


# --- the transfer-register feed (invariant 6) -------------------------------------


class TestTransferLogFormat:
    def _logformat(self) -> str:
        lines = [
            line for line in _conf().splitlines() if line.startswith("logformat intake_transfer")
        ]
        assert len(lines) == 1, lines
        return lines[0]

    def test_access_log_uses_only_the_intake_transfer_format(self) -> None:
        access = [line for line in _conf().splitlines() if line.startswith("access_log ")]
        assert len(access) == 1, access
        assert access[0].endswith(" intake_transfer")

    def test_format_carries_the_register_fields(self) -> None:
        line = self._logformat()
        for field in ("ts=", "host=%>rd", "port=%>rP", "decision=%Ss", "bytes_out=%>st"):
            assert field in line, f"{field} missing from the transfer record"

    def test_format_carries_no_path_or_query_code(self) -> None:
        line = self._logformat()
        for code in PATH_BEARING_CODES:
            assert code not in line, (
                f"{code} logs a URL path or query — invariant 6 keeps identifiers out "
                "of the transfer record"
            )

    def test_format_carries_no_client_identity_code(self) -> None:
        # >a/>A/un are the client address, FQDN and user name. The register
        # records a transfer to a vendor, not who inside made it.
        line = self._logformat()
        for code in ("%>a", "%>A", "%[un", "%un", "%ul", "%>eui"):
            assert code not in line, f"{code} identifies the caller"


# --- the renderer itself ----------------------------------------------------------


class TestRenderer:
    def test_render_is_deterministic(self) -> None:
        allowlist = _allowlist()
        assert render_squid_conf(allowlist, tier="dev") == render_squid_conf(allowlist, tier="dev")

    def test_regeneration_is_idempotent(self) -> None:
        # `python -m intake_platform.egress_proxy` is the only sanctioned way
        # to change the conf; running it on a clean tree must change nothing.
        before = SQUID_CONF_PATH.read_bytes()
        assert main() == 0
        assert SQUID_CONF_PATH.read_bytes() == before

    def test_two_rows_that_slugify_alike_are_refused_not_merged(self) -> None:
        # squid ACL names are derived from the row name; a silent merge would
        # give one vendor another's rule.
        collision = EgressAllowlist.model_validate(
            {
                "version": 1,
                "tiers": {
                    "dev": [
                        {
                            "name": "pypi-files",
                            "host": "files.pythonhosted.org",
                            "port": 443,
                            "protocol": "https",
                            "purpose": "unit fixture",
                            "basis": "unit fixture",
                        },
                        {
                            "name": "pypi.files",
                            "host": "files.example.org",
                            "port": 443,
                            "protocol": "https",
                            "purpose": "unit fixture",
                            "basis": "unit fixture",
                        },
                    ],
                    "phi_path": [],
                },
            }
        )
        with pytest.raises(ValueError, match="same squid ACL name"):
            render_squid_conf(collision, tier="dev")

    def test_render_refuses_an_unknown_tier(self) -> None:
        with pytest.raises(ValueError, match="tier"):
            render_squid_conf(_allowlist(), tier="production")  # type: ignore[arg-type]

    def test_render_refuses_a_list_a_vendor_pin_would_reject(self) -> None:
        # the renderer runs assert_dev_only_vendors first, so a squid.conf can
        # never be generated for an allow-list the library itself refuses.
        from intake_platform.egress import EgressConfigError

        poisoned = EgressAllowlist.model_validate(
            {
                "version": 1,
                "tiers": {
                    "dev": [],
                    "phi_path": [
                        {
                            "name": "llm",
                            "host": "llm.openai.com",
                            "port": 443,
                            "protocol": "https",
                            "purpose": "unit fixture",
                            "basis": "unit fixture",
                        }
                    ],
                },
            }
        )
        with pytest.raises(EgressConfigError):
            render_squid_conf(poisoned, tier="phi_path")
