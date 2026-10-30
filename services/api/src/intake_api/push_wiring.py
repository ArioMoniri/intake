"""INT-583 — wiring the APNs push gateway, or saying why there is none.

``push_gateway_from_settings`` returns the gateway only when every piece is in
place, checked cheapest and least sensitive first:

1. HTTP/2 support (``h2``): APNs speaks nothing else.
2. A route: on the synthetic host every network is internal, so the dedicated
   push-only proxy (``push-egress``, ADR-042's pattern) must be named, and it
   must be exactly the one ``intake_platform.egress`` admits for this purpose.
   Anywhere else a named proxy must be that one too, or none.
3. The egress policy: a PHI-tier row for this purpose and host, with the
   runtime gate open. No row ships until the owner applies one.
4. The key, read from OpenBao ``secret/api/apns`` only after the policy admits
   the host, so a refused host never has the key pulled into memory.

Anything missing is a typed :class:`~intake_api.push_port.PushUnconfigured`,
one log line naming the reason (never a value), and the notice fails closed.
"""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import Any, Protocol

import httpx
import yaml
from intake_platform.egress import (
    DEDICATED_PERSONAL_PROXIES,
    EgressConfigError,
    EgressPolicy,
    assert_dev_only_vendors,
    load_allowlist,
)
from intake_platform.secrets import SecretsBootError, SecretsProvider

from intake_api.push_apns import (
    APNS_HOSTS,
    APNS_KV_PATH,
    APNS_PORT,
    PUSH_EGRESS,
    ApnsConfigError,
    ApnsCredentials,
    ApnsPushGateway,
    apns_environment,
)
from intake_api.push_port import PushUnconfigured
from intake_api.settings import ApiSettings
from intake_api.sms_recipients import SYNTHETIC_ENVIRONMENTS

__all__ = ["PUSH_PROXY", "KvSecrets", "push_gateway_from_settings"]

logger = logging.getLogger("intake_api.push_wiring")

#: The one proxy a push call may ride (exact string, intake_platform.egress).
PUSH_PROXY = DEDICATED_PERSONAL_PROXIES[PUSH_EGRESS.purpose]


class KvSecrets(Protocol):
    """The slice of :class:`intake_platform.secrets.SecretsProvider` used here."""

    def get_kv(self, path: str) -> dict[str, Any]: ...


def _push_egress_policy(path: Path, host: str) -> EgressPolicy | None:
    """The PHI-tier policy, or None when it does not admit APNs: no row for
    this purpose and host, or the runtime PHI gate shut."""
    try:
        allowlist = load_allowlist(path)
        assert_dev_only_vendors(allowlist)
    except (OSError, ValueError, EgressConfigError, yaml.YAMLError) as exc:
        logger.warning(
            "push channel unconfigured: the egress allow-list is unusable (%s)", type(exc).__name__
        )
        return None
    policy = EgressPolicy.for_tier(allowlist, "phi_path")
    decision = policy.check(host, APNS_PORT, PUSH_EGRESS)
    if not decision.allowed:
        logger.warning(
            "push channel unconfigured: the egress policy refuses APNs until the owner "
            "applies its row (%s)",
            decision.reason,
        )
        return None
    return policy


def _document_from_vault(secrets: KvSecrets | None) -> dict[str, Any] | None:
    try:
        vault = secrets if secrets is not None else SecretsProvider.from_env()
        return vault.get_kv(APNS_KV_PATH)
    except (SecretsBootError, httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        logger.warning(
            "push channel unconfigured: the APNs key is not readable from OpenBao secret/%s (%s)",
            APNS_KV_PATH,
            type(exc).__name__,
        )
    return None


def push_gateway_from_settings(
    settings: ApiSettings, secrets: KvSecrets | None = None
) -> ApnsPushGateway | PushUnconfigured:
    """The APNs gateway, or the typed reason there is none (the notice then
    fails closed). The egress check runs before the vault read, so a host the
    policy refuses never has the key pulled into memory."""
    if importlib.util.find_spec("h2") is None:
        logger.warning("push channel unconfigured: HTTP/2 support (h2) is not installed")
        return PushUnconfigured.HTTP2_UNAVAILABLE
    proxy = settings.push_egress_proxy_url
    if proxy is not None and proxy != PUSH_PROXY:
        logger.warning(
            "push channel unconfigured: the push egress proxy is not the dedicated one "
            "intake_platform.egress admits"
        )
        return PushUnconfigured.NO_ROUTE
    if proxy is None and settings.environment in SYNTHETIC_ENVIRONMENTS:
        logger.warning(
            "push channel unconfigured on the synthetic host: no push egress proxy is "
            "named, and every network there is internal"
        )
        return PushUnconfigured.NO_ROUTE
    environment = apns_environment(settings.app_attest_environment)
    policy = _push_egress_policy(settings.egress_allowlist_path, APNS_HOSTS[environment])
    if policy is None:
        return PushUnconfigured.EGRESS_REFUSED
    document = _document_from_vault(secrets)
    if document is None:
        return PushUnconfigured.NO_CREDENTIALS
    try:
        credentials = ApnsCredentials.parse(document)
    except ApnsConfigError as exc:
        logger.warning("push channel unconfigured: %s", exc)
        return PushUnconfigured.MALFORMED_CREDENTIALS
    return ApnsPushGateway(
        credentials,
        topic=settings.app_attest_bundle_id,
        egress=policy,
        environment=environment,
        proxy=proxy,
    )
