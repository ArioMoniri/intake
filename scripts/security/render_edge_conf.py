"""Render infra/security/edge/edge-policy.yaml into the edge's deployed config.

INT-203, on the INT-018 arrangement: the policy has four enforcement points —
Traefik's dynamic configuration (the Coraza directives), CrowdSec's scenario
files, its acquisition, and cert-manager's ``Certificate`` — and four
hand-maintained copies of a security policy is the defect this script removes.
``--check`` fails when a committed file is stale, which is also what fails when
somebody edits a generated file instead of the policy.

Two renderings are deliberate about something that would otherwise be invisible:

- **The CRS is included whole, and the tuning is appended after it.** Coraza
  evaluates directives in order, so ``SecRuleUpdateTargetById`` must follow the
  ``Include`` that defined the rule. Rendering the exclusions first would make
  every one of them silently do nothing — a WAF that appears tuned and is not.
- **A ``Certificate`` is rendered only when the policy names a domain.** With
  ``domains: []`` the ``ClusterIssuer`` still renders (it needs no domain) and
  no ``Certificate`` does, so an empty list is an object that does not exist
  rather than an object with an empty ``dnsNames`` that cert-manager rejects at
  apply time, in a cluster, later.

Usage:
    uv run python scripts/security/render_edge_conf.py [--check]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "packages" / "intake_platform" / "src"))

from intake_platform.edge.policy import (  # noqa: E402
    EdgePolicy,
    load_edge_policy,
)

POLICY = REPO / "infra" / "security" / "edge" / "edge-policy.yaml"
EDGE = REPO / "infra" / "security" / "edge"
TRAEFIK_STATIC = EDGE / "traefik" / "traefik.yml"
TRAEFIK_DYNAMIC = EDGE / "traefik" / "dynamic.yml"
CROWDSEC_SCENARIO_DIR = EDGE / "crowdsec" / "scenarios"
CROWDSEC_ACQUIS = EDGE / "crowdsec" / "acquis.yaml"
CERT_MANAGER = REPO / "infra" / "k8s" / "edge" / "cert-manager.yaml"

_BANNER = """\
# GENERATED — do not edit by hand.
#
# Source:     infra/security/edge/edge-policy.yaml
# Generator:  scripts/security/render_edge_conf.py (`make edge-conf`)
# INT-203 / files/10 §4. Editing this file instead of the policy makes the
# deployed edge disagree with what review approved, and
# tests/infra/test_waf_rules.py fails.
"""


def coraza_directives(policy: EdgePolicy) -> list[str]:
    """The SecLang the Coraza middleware is handed, in evaluation order."""
    waf = policy.waf
    directives = [
        # Coraza's own recommended baseline: body access, the JSON body
        # processor, response limits. Included first because CRS assumes it.
        "Include @coraza.conf-recommended",
        f"SecRequestBodyLimit {waf.request_body_limit_bytes}",
        f"SecRequestBodyNoFilesLimit {waf.request_body_limit_bytes}",
        # CRS setup, then the whole ruleset. `@owasp_crs/*.conf` is the ruleset
        # embedded in the pinned plugin artefact — the "OWASP CRS suite" the
        # acceptance names, included entire rather than rule by rule, because a
        # hand-picked subset is a WAF whose coverage nobody can state.
        "Include @crs-setup.conf.example",
        (
            'SecAction "id:900000,phase:1,pass,nolog,'
            f"setvar:tx.blocking_paranoia_level={waf.paranoia_level},"
            f"setvar:tx.detection_paranoia_level={waf.paranoia_level},"
            f"setvar:tx.inbound_anomaly_score_threshold={waf.inbound_anomaly_threshold},"
            f'setvar:tx.outbound_anomaly_score_threshold={waf.outbound_anomaly_threshold}"'
        ),
        "Include @owasp_crs/*.conf",
        # Last, and only now: the tuning. Before the Include it would apply to
        # rules that do not exist yet and do nothing at all.
        f"SecRuleEngine {waf.engine}",
    ]
    for exclusion in waf.exclusions:
        directives.append(
            f'SecRuleUpdateTargetById {exclusion.rule_id} "!{exclusion.target}" "{exclusion.route}"'
        )
    return directives


def render_traefik_dynamic(policy: EdgePolicy) -> str:
    """Routers and the middleware chain, in the order a request meets them."""
    directives = "\n".join(
        f"            - {_quote(directive)}" for directive in coraza_directives(policy)
    )
    return f"""{_BANNER}
http:
  routers:
    # The one router. Host-based, on the local test name — the production
    # names live in the policy's `domains` and are empty until somebody
    # answers the ask in docs/evidence/INT-203.md §8.
    intake:
      rule: "Host(`{policy.tls.local_host}`)"
      entryPoints: [websecure, web]
      service: intake-api
      middlewares: [intake-waf, intake-headers]

  services:
    intake-api:
      loadBalancer:
        servers:
          - url: "http://api:8000"
        # A backend that is failing is not a backend to send clinical traffic
        # to; Traefik takes it out of rotation on the service's own probe
        # (CLAUDE.md invariant 13).
        healthCheck:
          path: /healthz
          interval: "10s"
          timeout: "3s"

  middlewares:
    intake-waf:
      plugin:
        coraza:
          directives:
{directives}

    intake-headers:
      headers:
        # The edge asserts the transport guarantees; the application asserts
        # its own CSP, which is nonce-based and cannot be written here
        # (files/08 §8).
        stsSeconds: 31536000
        stsIncludeSubdomains: true
        stsPreload: true
        contentTypeNosniff: true
        frameDeny: true
        referrerPolicy: "no-referrer"
        # Traefik advertises itself in `Server:` by default; the version of the
        # edge is not something a scanner needs from us.
        customResponseHeaders:
          Server: ""
          X-Powered-By: ""
"""


def _quote(directive: str) -> str:
    escaped = directive.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def render_traefik_static(policy: EdgePolicy) -> str:
    """Entry points, the plugin, the ACME resolver and the access log.

    Generated rather than hand-written for one reason: the CA directory, the
    challenge type and the storage path also appear in the cert-manager
    manifest, and a certificate that renews in one deployment shape and not
    the other is the exact drift files/10 §4 means by *"live configuration …
    not only a CI assertion"*.
    """
    tls = policy.tls
    waf = policy.waf
    return f"""{_BANNER}
entryPoints:
  web:
    address: ":80"
{_web_redirect(tls)}
  websecure:
    address: ":443"
    http:
      tls:
        certResolver: {tls.resolver}
  # Metrics and the liveness ping, on their own port so neither is reachable
  # from the internet entry points (files/10 §6; CLAUDE.md invariant 13).
  metrics:
    address: ":8082"

providers:
  file:
    directory: /etc/traefik/dynamic
    watch: true

# The Coraza middleware, loaded from disk. `localPlugins` takes the module from
# /plugins-local rather than from Traefik's plugin catalogue, so the edge boots
# with no network call and the artefact it executes is the one `make
# edge-plugin` verified against sha256 {waf.wasm_sha256[:16]}… .
experimental:
  localPlugins:
    coraza:
      moduleName: github.com/corazawaf/coraza-http-wasm

certificatesResolvers:
  {tls.resolver}:
    acme:
      caServer: {tls.ca_server}
      storage: {tls.storage}
      keyType: {_acme_key_type(tls.key_algorithm)}
      # The account email comes from the environment, sourced from OpenBao at
      # deploy time; it has no default, so a tier started without it fails to
      # order loudly instead of serving something untrusted quietly
      # (env {tls.account_email_env}).
      {_challenge_block(tls.challenge)}

# ── The access log is a PHI surface (CLAUDE.md invariant 6) ──────────────────
# This is the file CrowdSec reads and the SIEM ships. Traefik's default writes
# the full request line, which on this API carries patient identifiers in the
# path and whatever a query string held. Field selection is `drop` by default
# and each kept field is an id, an enumeration or a number — the same closed
# shape the egress transfer register uses.
accessLog:
  filePath: /var/log/traefik/access.log
  format: json
  fields:
    defaultMode: drop
    names:
      StartUTC: keep
      ClientHost: keep
      RequestMethod: keep
      RequestProtocol: keep
      DownstreamStatus: keep
      Duration: keep
      RouterName: keep
      ServiceName: keep
    headers:
      defaultMode: drop

log:
  level: INFO
  format: json

# `/metrics` for the WAF and CrowdSec block counters files/10 §7 names, on its
# own entry point so the series are never reachable from the internet.
metrics:
  prometheus:
    entryPoint: metrics
    addEntryPointsLabels: true
    addServicesLabels: true

ping:
  entryPoint: metrics
"""


def _web_redirect(tls: object) -> str:
    """Redirect :80 to :443 only once there is a certificate to redirect to.

    With ``domains: []`` no certificate is ordered, so an unconditional
    redirect would send every request to an entry point that cannot complete a
    handshake — a tier that looks configured and answers nothing. The redirect
    appears the day a domain does, from the same policy edit.
    """
    domains = getattr(tls, "domains", [])
    if not domains:
        return (
            "    # No `domains` in the policy means no certificate, so :80 is not\n"
            "    # redirected to an entry point that cannot complete a handshake.\n"
            "    # The redirect renders the day a domain does."
        )
    return (
        "    http:\n"
        "      redirections:\n"
        "        entryPoint:\n"
        "          to: websecure\n"
        "          scheme: https"
    )


def _challenge_block(challenge: str) -> str:
    if challenge == "tlsChallenge":
        return "tlsChallenge: {}"
    if challenge == "httpChallenge":
        return "httpChallenge:\n        entryPoint: web"
    return "dnsChallenge:\n        provider: exec"


def _acme_key_type(algorithm: str) -> str:
    return {"ECDSA-P256": "EC256", "ECDSA-P384": "EC384"}.get(algorithm, "RSA4096")


def render_crowdsec_scenarios(policy: EdgePolicy) -> dict[Path, str]:
    """One file per scenario, which is the shape CrowdSec's hub uses.

    Not one multi-document file: CrowdSec's local inventory keys on the file,
    so three documents in one file load as one scenario and the other two are
    silently absent — a tier that reports "scenarios on" and runs a third of
    them. Found by booting it (docs/evidence/INT-203.md §5).
    """
    rendered: dict[Path, str] = {}
    for scenario in policy.crowdsec.scenarios:
        slug = scenario.name.split("/", 1)[1]
        rendered[CROWDSEC_SCENARIO_DIR / f"{slug}.yaml"] = f"""{_BANNER}
# Signal: {scenario.signal}
type: {scenario.type}
name: {scenario.name}
description: "{scenario.description}"
filter: "{scenario.filter}"
groupby: "{scenario.groupby}"
capacity: {scenario.capacity}
leakspeed: {scenario.leakspeed}
blackhole: {scenario.blackhole}
labels:
  service: http
  remediation: {str(scenario.remediation).lower()}
"""
    return rendered


def render_crowdsec_acquis(policy: EdgePolicy) -> str:
    return f"""{_BANNER}
filenames:
  - {policy.crowdsec.acquisition_path}
labels:
  type: {policy.crowdsec.acquisition_type}
"""


def render_cert_manager(policy: EdgePolicy) -> str:
    """The cluster half of "certs automated" (INT-201's tier).

    The issuer always renders; the certificate renders only when a domain
    exists to order one for.
    """
    tls = policy.tls
    text = f"""{_BANNER}
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: {tls.issuer_name}
spec:
  acme:
    server: {tls.ca_server}
    # The account key cert-manager creates and keeps; the account email is
    # supplied at apply time from OpenBao, never committed (invariant 14).
    privateKeySecretRef:
      name: {tls.issuer_name}-account-key
    solvers:
      - http01:
          ingress:
            class: traefik
"""
    if not tls.domains:
        text += """
# No Certificate is rendered: infra/security/edge/edge-policy.yaml names no
# domain, because no production hostname for this system exists yet. An empty
# `dnsNames` is refused by cert-manager at apply time, in a cluster, later —
# so the object is absent rather than present and broken. The ask is in
# docs/evidence/INT-203.md §8.
"""
        return text
    names = "\n".join(f"    - {domain}" for domain in tls.domains)
    return (
        text
        + f"""---
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: {tls.secret_name}
spec:
  secretName: {tls.secret_name}
  issuerRef:
    name: {tls.issuer_name}
    kind: ClusterIssuer
  privateKey:
    algorithm: {tls.key_algorithm.split("-")[0]}
    size: {_key_size(tls.key_algorithm)}
  renewBefore: {tls.renew_before_days * 24}h
  dnsNames:
{names}
"""
    )


def _key_size(algorithm: str) -> int:
    return int(algorithm.rsplit("-", 1)[1].lstrip("P"))


def render_all(policy: EdgePolicy) -> dict[Path, str]:
    rendered: dict[Path, str] = {
        TRAEFIK_STATIC: render_traefik_static(policy),
        TRAEFIK_DYNAMIC: render_traefik_dynamic(policy),
        CROWDSEC_ACQUIS: render_crowdsec_acquis(policy),
        CERT_MANAGER: render_cert_manager(policy),
    }
    rendered.update(render_crowdsec_scenarios(policy))
    return rendered


def orphan_scenarios(policy: EdgePolicy) -> list[Path]:
    """Scenario files on disk that the policy no longer declares.

    Deleting a scenario from the policy has to delete the file, or CrowdSec
    keeps running a bucket nobody approved — the mirror image of adding one,
    and the direction a renderer that only ever writes will never notice.
    """
    expected = set(render_crowdsec_scenarios(policy))
    if not CROWDSEC_SCENARIO_DIR.exists():
        return []
    return sorted(p for p in CROWDSEC_SCENARIO_DIR.glob("*.yaml") if p not in expected)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero when a committed file differs from the render",
    )
    args = parser.parse_args(argv)

    policy = load_edge_policy(POLICY)
    rendered = render_all(policy)
    stale: list[Path] = list(orphan_scenarios(policy))
    if not args.check:
        for orphan in stale:
            orphan.unlink()
            print(f"removed {orphan.relative_to(REPO)} (no longer in the policy)")
        stale = []
    for path, text in rendered.items():
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current == text:
            continue
        if args.check:
            stale.append(path)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(f"wrote {path.relative_to(REPO)}")

    if stale:
        for path in stale:
            print(f"STALE: {path.relative_to(REPO)}", file=sys.stderr)
        print(
            "run `make edge-conf` — the edge policy and the deployed configuration have diverged",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
