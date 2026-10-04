"""The closed allow-list of metric label keys (INT-481; CLAUDE.md invariant 6).

A metric label is where a free-text value would reach Prometheus, and from
there every dashboard, rule and console tile that reads it. Invariant 6 says
no PHI or PII in metrics; :data:`intake_platform.slo.PHI_RISK_LABEL_NAMES`
refuses the obvious names at the catalogue schema. This module is the other
half: ONE closed list of every label key the platform may produce or read,
held by tests/observability/test_metric_labels.py against the catalogue, every
committed rule file, every committed dashboard and the staging Prometheus,
whose scrape jobs keep exactly this list at ingestion (``labelkeep``) so a key
nobody reviewed is never stored, whatever a service or an exporter sends.

The list is itself held to a refusal rule (:func:`label_key_problem`):

- a key with a segment that names a person, a session or a device
  (``patient``, ``user``, ``email``, ``session``, ``device``, ``ip``…) is
  refused;
- a key whose last segment carries free text (``name``, ``text``,
  ``message``, ``path``, ``url``…) is refused — ``message_class`` is a class,
  ``patient_name`` is a name;
- a key whose last segment is identifier-shaped (``id``, ``sha``, ``hash``,
  ``token``, ``number``…) is refused,

unless it is one of :data:`REVIEWED_IDENTIFIER_KEYS`, each of which says why
its values name no patient. Adding a key to the list is a reviewed diff here;
nothing derives the list from what happens to be emitted.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from typing import Any, Final

import yaml

from intake_platform.slo import PHI_RISK_LABEL_NAMES

__all__ = [
    "ALLOWED_LABEL_KEYS",
    "REVIEWED_IDENTIFIER_KEYS",
    "STRUCTURAL_LABEL_KEYS",
    "dashboard_label_keys",
    "label_key_problem",
    "labelkeep_regex",
    "promql_label_keys",
    "rule_label_keys",
]

#: Keys Prometheus itself attaches or reads: the series name, the scrape
#: target's job and instance, histogram and summary buckets, and the two keys
#: of the synthetic ``ALERTS`` series.
STRUCTURAL_LABEL_KEYS: Final = frozenset(
    {"__name__", "job", "instance", "le", "quantile", "alertname", "alertstate"}
)

#: Identifier-shaped keys that were reviewed one by one. Each value says what
#: the label holds and why that names no patient.
REVIEWED_IDENTIFIER_KEYS: Final[Mapping[str, str]] = {
    "actor": "a staff account subject from the admin realm, never a patient (INT-180)",
    "budget_id": "a budget id from infra/costs/unit-prices.yaml, a configuration name (INT-190)",
    "head_sha": "a git commit sha of this repository, from CI or a deploy",
    "host_id": "the operator's id for a model host, refused unless id-shaped, never an address",
    "key": "a Transit key name, tenant-<tenant id>, a tenant and never a person (INT-367)",
    "run_number": "a GitHub Actions run number of this repository",
    "tenant": "a tenant (deployment) id, an organisation and never a person",
}

#: Every label key the platform may produce or read. Closed: a new key is a
#: reviewed edit of this set, and the refusal rule below must pass on it.
ALLOWED_LABEL_KEYS: Final = STRUCTURAL_LABEL_KEYS | frozenset(
    {
        "action",
        "actor",
        "adapter",
        "age_band",
        "asn",
        "blocker",
        "branch",
        "budget_id",
        "change",
        "channel",
        "class",
        "code",
        "complete",
        "component",
        "conclusion",
        "control",
        "cpu",
        "data_class",
        "direction",
        "document_type",
        "endpoint",
        "event",
        "experiment",
        "field",
        "from_component",
        "from_state",
        "gate",
        "gateway",
        "generation",
        "gpu_index",
        "group",
        "guardrail",
        "head_sha",
        "host_id",
        "implementation",
        "instrument",
        "key",
        "kind",
        "lane",
        "level",
        "locale",
        "major",
        "message_class",
        "method",
        "minor",
        "mode",
        "new_level",
        "outcome",
        "pack",
        "patchlevel",
        "period",
        "phase",
        "pr",
        "privileged",
        "profile",
        "queue",
        "reason",
        "reason_class",
        "route",
        "rule",
        "run_number",
        "scope",
        "section",
        "service",
        "severity",
        "signal",
        "slo",
        "source",
        "spec",
        "stage",
        "state",
        "status",
        "step",
        "stream",
        "subject_count",
        "tag",
        "target",
        "tenant",
        "to",
        "to_component",
        "to_state",
        "tool",
        "trigger",
        "type",
        "under_grant",
        "vendor",
        "version",
        "view",
        "vital",
        "voice",
        "window",
        "workflow",
    }
)

#: A segment anywhere in the key that ties the value to a person, a session or
#: a device.
_PERSON_SEGMENTS: Final = frozenset(
    {
        "actor",
        "address",
        "birth",
        "client",
        "cookie",
        "device",
        "dob",
        "email",
        "ip",
        "msisdn",
        "national",
        "patient",
        "person",
        "phone",
        "session",
        "tckn",
        "transcript",
        "user",
        "username",
        "utterance",
    }
)
#: A last segment that carries free text.
_FREE_TEXT_TAILS: Final = frozenset(
    {
        "body",
        "comment",
        "content",
        "description",
        "message",
        "name",
        "note",
        "path",
        "payload",
        "query",
        "raw",
        "summary",
        "text",
        "title",
        "uri",
        "url",
        "value",
    }
)
#: A last segment that is identifier-shaped.
_IDENTIFIER_TAILS: Final = frozenset(
    {
        "fingerprint",
        "guid",
        "hash",
        "id",
        "ids",
        "key",
        "number",
        "sha",
        "sub",
        "subject",
        "token",
        "uuid",
    }
)
_KEY_RE: Final = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def label_key_problem(
    key: str, *, reviewed: Iterable[str] = REVIEWED_IDENTIFIER_KEYS
) -> str | None:
    """Why ``key`` may not be a metric label, or ``None`` when the shape rule admits it.

    ``reviewed`` is the exception list; the default is the committed one. A
    test passes an empty one to prove each exception is load-bearing.
    """
    if _KEY_RE.match(key) is None:
        return f"{key!r} is not a Prometheus label name"
    if key in PHI_RISK_LABEL_NAMES:
        return f"{key!r} is a PHI-risk label name (intake_platform.slo)"
    if key in STRUCTURAL_LABEL_KEYS or key in set(reviewed):
        return None
    segments = [segment for segment in key.lower().split("_") if segment]
    person = sorted(set(segments) & _PERSON_SEGMENTS)
    if person:
        return f"{key!r} names a person, a session or a device ({', '.join(person)})"
    tail = segments[-1] if segments else ""
    if tail in _FREE_TEXT_TAILS:
        return f"{key!r} carries free text ({tail})"
    if tail in _IDENTIFIER_TAILS:
        return f"{key!r} is identifier-shaped ({tail}) and is not a reviewed identifier"
    return None


def labelkeep_regex(keys: Iterable[str] = ALLOWED_LABEL_KEYS) -> str:
    """The ``labelkeep`` regex a staging scrape job runs: exactly ``keys``, sorted."""
    return "|".join(sorted(keys))


# --- PromQL -------------------------------------------------------------------------------

_STRING_RE: Final = re.compile(r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|`[^`]*`')
_GROUPING_RE: Final = re.compile(
    r"\b(?:by|without|on|ignoring|group_left|group_right)\s*\(([^()]*)\)", re.IGNORECASE
)
_MATCHER_RE: Final = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*(?:=~|!~|!=|=)\s*\x00")
_LABEL_FUNCTIONS: Final = {"label_replace": (1, 3), "label_join": (1, None)}
_FUNCTION_RE: Final = re.compile(r"\b(label_replace|label_join)\s*\(")
_LEGEND_RE: Final = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


def _arguments(expr: str, open_paren: int) -> list[str]:
    """The top-level comma-separated arguments of the call opening at ``open_paren``."""
    depth = 0
    args: list[str] = []
    current: list[str] = []
    index = open_paren
    while index < len(expr):
        char = expr[index]
        if char in "\"'`":
            match = _STRING_RE.match(expr, index)
            literal = match.group(0) if match is not None else char
            current.append(literal)
            index += len(literal)
            continue
        if char in "([{":
            depth += 1
            if depth > 1:
                current.append(char)
        elif char in ")]}":
            depth -= 1
            if depth == 0:
                args.append("".join(current).strip())
                return args
            current.append(char)
        elif char == "," and depth == 1:
            args.append("".join(current).strip())
            current = []
        else:
            current.append(char)
        index += 1
    return args


def _unquote(text: str) -> str | None:
    match = _STRING_RE.fullmatch(text.strip())
    return match.group(0)[1:-1] if match is not None else None


def _function_label_keys(expr: str) -> Iterator[str]:
    for match in _FUNCTION_RE.finditer(expr):
        first, last = _LABEL_FUNCTIONS[match.group(1)]
        args = _arguments(expr, match.end() - 1)
        positions = [first] + (list(range(3, len(args))) if last is None else [last])
        for position in positions:
            if position < len(args):
                value = _unquote(args[position])
                if value:
                    yield value


def promql_label_keys(expr: str) -> frozenset[str]:
    """Every label key a PromQL expression selects, groups by or writes.

    Selector matchers (``{a="x", b=~"y"}``), grouping and vector-matching
    clauses (``by``/``without``/``on``/``ignoring``/``group_left``/
    ``group_right``) and the label arguments of ``label_replace`` and
    ``label_join``. String literals are blanked first, so text inside a
    matcher's value is never read as a key.
    """
    keys: set[str] = set(_function_label_keys(expr))
    blanked = _STRING_RE.sub("\x00", expr)
    for selector in re.findall(r"\{([^{}]*)\}", blanked):
        keys.update(_MATCHER_RE.findall(selector))
    for clause in _GROUPING_RE.findall(blanked):
        keys.update(part.strip() for part in clause.split(",") if part.strip())
    return frozenset(keys)


def _walk(node: Any) -> Iterator[tuple[str, Any]]:
    if isinstance(node, dict):
        for key, value in node.items():
            yield str(key), value
            yield from _walk(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item)


def dashboard_label_keys(dashboard: Mapping[str, Any]) -> frozenset[str]:
    """Every label key a Grafana dashboard reads.

    Every ``expr`` (panel targets and annotation queries) through
    :func:`promql_label_keys`, and every ``{{key}}`` in a ``legendFormat``,
    ``titleFormat`` or ``textFormat``, plus an annotation's ``tagKeys``.
    """
    keys: set[str] = set()
    for field, value in _walk(dashboard):
        if not isinstance(value, str):
            continue
        if field == "expr":
            keys.update(promql_label_keys(value))
        elif field in {"legendFormat", "titleFormat", "textFormat"}:
            keys.update(_LEGEND_RE.findall(value))
        elif field == "tagKeys":
            keys.update(part.strip() for part in value.split(",") if part.strip())
    return frozenset(keys)


def rule_label_keys(path: Path) -> frozenset[str]:
    """Every label key a Prometheus rule file declares or reads."""
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    keys: set[str] = set()
    for group in loaded.get("groups") or []:
        for rule in group.get("rules") or []:
            keys.update(promql_label_keys(str(rule.get("expr", ""))))
            keys.update(str(key) for key in (rule.get("labels") or {}))
    return frozenset(keys)
