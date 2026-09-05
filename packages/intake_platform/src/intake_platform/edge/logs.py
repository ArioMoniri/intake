"""The edge log boundary: a WAF block is a signal, not a disclosure (INT-203).

Coraza writes one line per matching rule, and CRS rules carry ``logdata``. A
real line from the booted tier, captured into
``tests/fixtures/waf/coraza-blocks.log``, reads in part::

    [id "942100"] [msg "SQL Injection Attack Detected via libinjection"]
    [data "Matched Data: sUEv, found within ARGS:json.text_tr: Göğsümde şiddetli
           ağrı var' UNION SELECT null,version(),null-- ve nefes darlığı"]
    [uri "/v1/intake/utterance"] [unique_id "PBQUwiXcobicrCsgOXl"]

``ARGS:json.text_tr`` is the patient's utterance. On a JSON API whose one
free-text field carries the reason a person is seeing a doctor, ``data`` is a
clinical sentence and ``uri`` is a path plus whatever the query string held.
Shipping that line to the SIEM trades an injection attempt for a PHI
disclosure — and it is *worse* than the attempt, because the disclosure
succeeds, is durable, and looks exactly like a security control working.

The answer is the one :class:`~intake_platform.egress.TransferRecord` uses:
**a closed record with no field a sentence could occupy.** This module does not
redact the line — redaction is a filter, and a filter that misses once has
leaked. It parses out the six values that are constants of the ruleset (rule
id, its CRS family, severity, the CRS version, the anomaly score, and the
request's opaque correlation id) and never reads ``data``, ``msg``,
``logdata``, ``uri``, ``hostname`` or ``client`` at all.

The near-miss control is in ``tests/infra/test_waf_rules.py``: a scrubber that
drops everything is exactly as useful as one that drops nothing, so the event
must still carry the rule id, the family and the block verdict.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from intake_platform.edge.policy import RuleClass

__all__ = ["EdgeEvent", "parse_coraza_line"]

#: ``[key "value"]`` pairs, as Coraza formats them. Only the keys named in
#: :data:`_READ` are ever looked up; the rest are not parsed, so there is no
#: code path along which ``data`` could reach an :class:`EdgeEvent`.
_FIELD_RE = re.compile(r'\[(?P<key>[a-z_]+)\s+"(?P<value>[^"]*)"\]')

#: The only keys this parser reads. Deliberately a frozenset rather than a
#: denylist: a new CRS field appearing in a future ruleset is ignored by
#: default, which is the direction that fails safe.
_READ = frozenset({"id", "severity", "ver", "unique_id", "file"})

#: ``Inbound Anomaly Score Exceeded (Total Score: 16)`` — a number, and the
#: only thing read out of the message.
_SCORE_RE = re.compile(r"Total Score:\s*(\d+)")

#: ``[ver "OWASP_CRS/4.0.0"]``.
_VER_RE = re.compile(r"OWASP_CRS/(\d+\.\d+\.\d+)")

#: ``@owasp_crs/REQUEST-942-APPLICATION-ATTACK-SQLI.conf`` -> the family. The
#: file name is a constant of the ruleset, which is what makes it safe to
#: keep: no part of it comes from the request.
_FILE_RE = re.compile(r"(?:REQUEST|RESPONSE)-(?P<number>\d{3})-")

_CLASS_BY_NUMBER = {
    "901": RuleClass.INITIALIZATION,
    "905": RuleClass.INITIALIZATION,
    "911": RuleClass.METHOD,
    "913": RuleClass.SCANNER,
    "920": RuleClass.PROTOCOL,
    "921": RuleClass.PROTOCOL,
    "922": RuleClass.PROTOCOL,
    "930": RuleClass.LFI,
    "931": RuleClass.RFI,
    "932": RuleClass.RCE,
    "933": RuleClass.PHP,
    "934": RuleClass.GENERIC,
    "941": RuleClass.XSS,
    "942": RuleClass.SQLI,
    "943": RuleClass.SESSION_FIXATION,
    "944": RuleClass.JAVA,
    "949": RuleClass.BLOCKING,
    "950": RuleClass.DATA_LEAKAGE,
    "951": RuleClass.DATA_LEAKAGE,
    "952": RuleClass.DATA_LEAKAGE,
    "953": RuleClass.DATA_LEAKAGE,
    "954": RuleClass.DATA_LEAKAGE,
    "955": RuleClass.DATA_LEAKAGE,
    "959": RuleClass.BLOCKING,
    "980": RuleClass.CORRELATION,
}

#: The phrase Coraza uses for an interruption, as opposed to a warning that
#: only added to the score. Matched on the fixed prefix, never on the tail.
_DENIED = "Coraza: Access denied"


@dataclass(frozen=True)
class EdgeEvent:
    """One WAF decision, in a shape with nowhere for a sentence to hide.

    Every field is an id, an enumeration or a number — the same discipline
    ``TransferRecord`` applies to the egress register. ``unique_id`` is
    Coraza's per-request correlation token: random, request-scoped, and the
    only way a responder can tie this event to the access-log line and to a
    CrowdSec bucket without any of the three carrying content.
    """

    rule_id: int
    rule_class: RuleClass
    severity: str
    crs_version: str
    anomaly_score: int | None
    unique_id: str
    blocked: bool


def _message(line: str) -> str | None:
    """The Coraza text, out of whatever Traefik wrapped it in.

    The edge logs JSON (``log.format: json`` in the rendered traefik.yml), so
    the rule line arrives as the ``message`` value of an object, with its
    quotes escaped. Parsing the envelope rather than the raw line is not
    cosmetic: a regex run over the escaped form matches nothing, and a parser
    that matches nothing returns no events, and an edge that reports no events
    is indistinguishable from one that is not being attacked.
    """
    text = line.strip()
    if not text:
        return None
    if not text.startswith("{"):
        return text
    try:
        envelope = json.loads(text)
    except ValueError:
        return None
    message = envelope.get("message")
    return message if isinstance(message, str) else None


def parse_coraza_line(line: str) -> EdgeEvent | None:
    """Turn one Coraza log line into an :class:`EdgeEvent`, or ``None``.

    ``None`` for anything that is not a rule match — Traefik's own startup
    lines, a comment in a fixture, an empty line, a truncated one. A line this
    parser does not understand is dropped rather than guessed at, because the
    alternative is shipping an unparsed line, which is the raw line, which is
    the leak.
    """
    message = _message(line)
    if message is None or "[id " not in message:
        return None
    line = message

    fields = {
        match.group("key"): match.group("value")
        for match in _FIELD_RE.finditer(line)
        if match.group("key") in _READ
    }
    raw_id = fields.get("id", "")
    if not raw_id.isdigit():
        return None

    file_match = _FILE_RE.search(fields.get("file", ""))
    rule_class = (
        _CLASS_BY_NUMBER.get(file_match.group("number"), RuleClass.OTHER)
        if file_match
        else RuleClass.OTHER
    )
    version_match = _VER_RE.search(fields.get("ver", ""))
    score_match = _SCORE_RE.search(line)

    return EdgeEvent(
        rule_id=int(raw_id),
        rule_class=rule_class,
        severity=fields.get("severity", "unknown"),
        crs_version=version_match.group(1) if version_match else "unknown",
        anomaly_score=int(score_match.group(1)) if score_match else None,
        unique_id=fields.get("unique_id", ""),
        blocked=_DENIED in line,
    )
