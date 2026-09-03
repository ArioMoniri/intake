"""Connector signals (files/10 §9 `connectors` row; CLAUDE.md invariant 13).

Three families, every one catalogued in ``observability/metrics_catalog.yaml``
before it was constructed here. Labels are registry ids and closed
enumerations only: an ``endpoint`` label is bounded by the registry, and an
``outcome`` label by :class:`~intake_connectors.receipts.ReceiptState`. No
label is derived from anything a patient, a payload or a receiver supplied,
so the cardinality of this metric store is not something an attacker can
choose (invariant 6).
"""

from __future__ import annotations

from prometheus_client import Counter, Histogram

__all__ = [
    "CONNECTOR_PUSH_DURATION_SECONDS",
    "CONNECTOR_PUSH_TOTAL",
    "CONNECTOR_RECEIPTS_UNRESOLVED_TOTAL",
    "CONNECTOR_TOKEN_EXCHANGE_TOTAL",
]

CONNECTOR_PUSH_TOTAL = Counter(
    "connector_push_total",
    "Connector pushes by registered endpoint and settled receipt state.",
    ("endpoint", "outcome"),
)

CONNECTOR_PUSH_DURATION_SECONDS = Histogram(
    "connector_push_duration_seconds",
    "Wall time from the write-ahead receipt to its settlement, in seconds.",
    ("endpoint",),
)

#: The write-ahead cost, made countable: pushes whose outcome we do not know.
#: files/10 §9 wants endpoint errors visible; this is the subset that cannot
#: be resolved by looking at a status code, and it is the series that decides
#: whether a retry is safe.
CONNECTOR_RECEIPTS_UNRESOLVED_TOTAL = Counter(
    "connector_receipts_unresolved_total",
    "Pushes settled as unresolved — bytes may or may not have reached the receiver.",
    ("endpoint",),
)

#: INT-161. A SMART token exchange is a *separate* failure from a push
#: failure and has a separate fix — a key, a registration or an authorization
#: server outage rather than a bundle or a network — so files/10 §9's
#: "endpoint errors" signal needs to tell them apart. The outcome label is
#: bucketed into six of our own values rather than carrying a receiver's
#: status code, because a status is receiver-chosen and a label a receiver
#: chooses is cardinality a receiver chooses. The precise code still lands in
#: the receipt's `outcome_code`, which nothing indexes.
CONNECTOR_TOKEN_EXCHANGE_TOTAL = Counter(
    "connector_token_exchange_total",
    "SMART backend services token exchanges by registered endpoint and bucketed outcome.",
    ("endpoint", "outcome"),
)
