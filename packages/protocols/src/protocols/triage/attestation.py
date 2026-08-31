"""Provenance-authorised preemption: the files/12 §5 attestation (INT-269).

files/12 §5 puts an HMAC-SHA256 over every rules-engine verdict and then says,
in the same breath, who is allowed to hold it:

    The signing key is fetched from OpenBao **by the rules-engine subsystem
    alone**, and an import-boundary test asserts no module under
    ``extraction/``, ``observers/`` or ``talker/`` transitively imports the
    attestor.

INT-091 had put the attestor in the Talker, which is the one place that
sentence forbids, and the reason is not bureaucratic: **a signature verified by
the party that could forge it is not a signature.** With a symmetric MAC the
holder of the key is the holder of the capability, so the key — and therefore
this module — belongs to the only subsystem that may produce a level at all
(CLAUDE.md invariant 1). The Talker calls a verifier it does not own, through a
port wired at the composition root, and holds no key and no signing primitive;
``tests/safety/test_triage_attestation.py`` asserts that over the AST of every
file under ``services/voice-runtime/``, with negative controls proving each arm
of the gate can fail.

**What the MAC covers, and why more than files/12 §5's list.** The spec names
``(session_id, ek4, disposition, sorted rule_ids, inputs_hash, protocol_hash,
life_threat_version, engine_version, issued_at, nonce, key_id)``. Two
departures, both stated rather than silent:

- ``disposition`` is carried as :class:`~clinical_schemas.triage.TriageLevel`,
  the patient-routing determination that exists on this branch. files/12 §2.1's
  ``Disposition`` enum is not implemented anywhere in the repo yet; inventing a
  value for it here would be a placeholder in the one place a placeholder is
  most expensive (CLAUDE.md invariant 17). When that enum lands, it joins the
  claim as its own field and the domain constant below moves to ``v2``.
- ``register`` and ``location`` are covered **in addition**. A RED is three
  axes, not one (invariant 21); an ``ALERT`` verdict whose register can be
  flipped to ``SILENT`` without breaking the MAC is a forgeable axis on the
  path where being wrong is the harm. Adding covered fields tightens, never
  relaxes, and the claim's own axes are cross-checked against the verdict the
  caller is about to act on.

**Verification checks far more than MAC validity** (files/12 §5): the session
matches the live one, ``inputs_hash`` equals the hash of the context just
evaluated, ``protocol_hash`` equals the session's pinned hash, ``issued_at`` is
within five seconds and the nonce is unseen. That is what kills replay,
cross-session copy and stale-verdict resurrection rather than forgery alone.

**This is not a second route to a level** (invariant 1). :func:`attest` takes a
:class:`~protocols.triage.engine.TriageEvaluation` — the output of
:func:`~protocols.triage.engine.evaluate_triage`, the only producer of a level —
and has no parameter that could set one. :func:`verify` returns ``None``: it
authenticates a determination that already exists and hands nothing back that
could be mistaken for one.

**The metric is declared, not emitted.** ``safety.forged_triage_total`` has no
row in ``observability/metrics_catalog.yaml`` on this branch, and invariant 13
is row-first: a series constructed before it is catalogued fails CI and is a
defect even when it does not. So refusals are counted in process on
:class:`ForgedTriageTally`, whose only label is a closed refusal reason —
never a session, a slot or anything a patient said (invariant 6).
"""

from __future__ import annotations

import base64
import enum
import hashlib
import hmac
import warnings
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from secrets import token_hex
from typing import Any, Final, NoReturn, Protocol, runtime_checkable

from clinical_schemas.common import FrozenModel, Ref, Sha256
from clinical_schemas.triage import RedLocation, RedRegister, RulesTriageResult, TriageLevel
from pydantic import AwareDatetime, Field, model_validator

from protocols.triage.context import TriageContext, render_slot_value
from protocols.triage.engine import TriageEvaluation
from protocols.types import EK4Level

__all__ = [
    "ATTESTATION_KV_PATH",
    "FORGED_TRIAGE_TOTAL",
    "FRESHNESS_WINDOW",
    "MIN_KEY_BYTES",
    "NONCE_BYTES",
    "AttestationKeyring",
    "AttestationRefused",
    "ForgedTriageTally",
    "KeyringBootError",
    "KvSecrets",
    "MetricDeclaration",
    "NonceLedger",
    "RefusalReason",
    "TriageAttestation",
    "TriageClaim",
    "UnknownKeyId",
    "attest",
    "context_inputs_hash",
    "keyring_from_secrets",
    "new_nonce",
    "verify",
]

#: Where the rules engine's signing keys live in OpenBao KV v2 (files/10 §2:
#: secrets come from the vault, never from an environment variable and never
#: from code). The bundle is ``{"active_key_id": "<id>", "keys": {"<id>":
#: "<base64>"}}`` — a key set rather than a key, so rotation is a new id
#: alongside the old one, exactly as ``intake_platform.tokenization`` rotates.
ATTESTATION_KV_PATH: Final = "triage/attestation"

#: HMAC-SHA256 gains nothing from a key longer than its block size and loses
#: security below its output size; 32 bytes is the floor a shorter key fails.
MIN_KEY_BYTES: Final = 32

#: files/12 §5 — *"``issued_at`` is within 5 s"*. Applied in both directions:
#: a verdict from the future is as wrong as a stale one, and tolerating one
#: would hand an attacker an unbounded window by moving a clock forward.
FRESHNESS_WINDOW: Final = timedelta(seconds=5)

#: 128 bits of nonce: the collision probability across every attestation a
#: fleet could issue inside one five-second window is not a real number.
NONCE_BYTES: Final = 16

#: Domain separation. A MAC is only unambiguous inside the domain it was
#: computed for; this constant is what stops a digest over some other
#: length-prefixed structure from ever being read as an attestation.
_DOMAIN: Final = b"intake.triage.attestation.v1"


@dataclass(frozen=True)
class MetricDeclaration:
    """A metric this module *has committed to emit*, declared before a row for
    it exists in ``observability/metrics_catalog.yaml`` (invariant 13: the row
    comes first, the emission second). Nothing here constructs a Prometheus
    family — that is the change that lands with the catalogue row."""

    id: str
    name: str
    labels: tuple[str, ...]
    unit: str
    owner: str
    description: str


#: files/12 §5's counter. One label, a closed enumeration of refusal reasons:
#: no session id, no rule id, no slot key, nothing a patient said (invariant 6).
FORGED_TRIAGE_TOTAL: Final = MetricDeclaration(
    id="safety.forged_triage_total",
    name="safety_forged_triage_total",
    labels=("reason",),
    unit="count",
    owner="safety",
    description=(
        "Triage attestations refused by the rules-engine verifier, by closed "
        "refusal reason (files/12 §5 seven-way mutation)."
    ),
)


class RefusalReason(enum.StrEnum):
    """Why one attestation was refused — the counter's only label value."""

    UNKNOWN_KEY = "unknown_key"
    BAD_MAC = "bad_mac"
    VERDICT_MISMATCH = "verdict_mismatch"
    SESSION_MISMATCH = "session_mismatch"
    INPUTS_MISMATCH = "inputs_mismatch"
    PROTOCOL_MISMATCH = "protocol_mismatch"
    STALE = "stale"
    NONCE_REUSE = "nonce_reuse"


class KeyringBootError(Exception):
    """The signing keys are absent or unusable, so nothing can be attested.

    Fails closed at construction, as ``intake_platform.secrets`` does: a
    service that cannot attest must not start rather than start unattested.
    The offending value is never echoed — it is key material.
    """


class UnknownKeyId(KeyError):
    """A key id that is not in the keyring. Distinct from a bad MAC: the
    verdict may be genuine and signed under a key this process has not been
    given (a rotation the caller has not picked up), which is a different
    operational story from a forgery."""


class AttestationRefused(PermissionError):
    """An attestation did not verify. Nothing is spoken and nothing is acted on.

    Carries a closed :class:`RefusalReason` and a message that names no
    session, no slot and no patient content (invariant 6).
    """

    def __init__(self, reason: RefusalReason, message: str) -> None:
        self.reason: Final = reason
        super().__init__(f"{reason.value}: {message}")


class ForgedTriageTally:
    """In-process count of refusals by reason — ``safety.forged_triage_total``
    before it has a catalogue row. Injected rather than global so a test, a
    session and a process can each hold their own."""

    def __init__(self) -> None:
        self._counts: dict[RefusalReason, int] = {}

    def record(self, reason: RefusalReason) -> None:
        self._counts[reason] = self._counts.get(reason, 0) + 1

    def count(self, reason: RefusalReason) -> int:
        return self._counts.get(reason, 0)

    @property
    def total(self) -> int:
        return sum(self._counts.values())

    @property
    def by_reason(self) -> Mapping[RefusalReason, int]:
        return dict(self._counts)


# --- the key source: injected, from OpenBao, never an environment variable ---


@runtime_checkable
class KvSecrets(Protocol):
    """The slice of ``intake_platform.secrets.SecretsProvider`` used here.

    A structural port, for the same reason ``intake_platform.ehrbase`` declares
    one: ``packages/protocols`` does not depend on the platform package, and a
    test must be able to supply a recorded bundle without a live OpenBao.
    """

    def get_kv(self, path: str) -> Mapping[str, Any]: ...


class AttestationKeyring:
    """The rules engine's signing keys, held by id so rotation is additive."""

    def __init__(self, keys: Mapping[str, bytes], active_key_id: str) -> None:
        for key_id, material in keys.items():
            if len(material) < MIN_KEY_BYTES:
                raise KeyringBootError(
                    f"attestation key {key_id!r} is shorter than {MIN_KEY_BYTES} bytes; "
                    "the value is not echoed"
                )
        if active_key_id not in keys:
            raise KeyringBootError(
                f"active attestation key id {active_key_id!r} is not in the key set"
            )
        self._keys = dict(keys)
        self.active_key_id: Final = active_key_id

    @property
    def key_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._keys))

    def signing_key(self, key_id: str) -> bytes:
        try:
            return self._keys[key_id]
        except KeyError:
            raise UnknownKeyId(f"no attestation key with id {key_id!r}") from None

    def __repr__(self) -> str:
        """Ids only. A keyring that renders its keys puts them in every
        exception message, log line and traceback that ever holds one."""
        return f"AttestationKeyring(key_ids={self.key_ids!r}, active_key_id={self.active_key_id!r})"


def keyring_from_secrets(secrets: KvSecrets, path: str = ATTESTATION_KV_PATH) -> AttestationKeyring:
    """Read the keyring from OpenBao. The only supported production source."""
    bundle = secrets.get_kv(path)
    active = bundle.get("active_key_id")
    raw_keys = bundle.get("keys")
    if not isinstance(active, str) or not active:
        raise KeyringBootError(
            f"OpenBao secret/{path} carries no active_key_id — the rules engine "
            "refuses to attest rather than guess which key is current"
        )
    if not isinstance(raw_keys, Mapping) or not raw_keys:
        raise KeyringBootError(f"OpenBao secret/{path} carries no keys")
    keys: dict[str, bytes] = {}
    for key_id, encoded in raw_keys.items():
        if not isinstance(encoded, str):
            raise KeyringBootError(f"attestation key {key_id!r} is not a base64 string")
        try:
            keys[key_id] = base64.b64decode(encoded, validate=True)
        except ValueError as err:
            raise KeyringBootError(
                f"attestation key {key_id!r} is not valid base64; the value is not echoed"
            ) from err
    return AttestationKeyring(keys, active)


# --- what is signed ----------------------------------------------------------


# The blueprint names the RED axis field `register` (CLAUDE.md invariant 21;
# files/02 §5.3); pydantic warns because ABCMeta exposes a classmethod of the
# same name. The blueprint name wins here as it does on every model that
# carries the axis (clinical_schemas.triage, intake_voice_runtime.talker).
warnings.filterwarnings(
    "ignore",
    message='Field name "register" in "TriageClaim" shadows an attribute in parent',
    category=UserWarning,
)


class TriageClaim(FrozenModel):
    """The signed statement: this verdict, for this session, over these inputs.

    Every field is covered by the MAC. Nothing here is patient content: rule
    ids, hashes, versions and a nonce, which is also why an attestation is safe
    to carry through a queue and an audit row (invariant 6).
    """

    session_id: Ref = Field(description="The live session this verdict belongs to.")
    ek4: EK4Level = Field(description="EK-4 acuity of the evaluation (files/12 §2.1).")
    level: TriageLevel = Field(
        description="Patient-routing determination — files/12 §5's `disposition` "
        "as it exists on this branch; §2.1's Disposition enum is not implemented "
        "yet and is not invented here."
    )
    rule_ids: tuple[str, ...] = Field(
        default=(),
        description="Ids of the rules that fired, sorted and unique (files/12 §5).",
    )
    register: RedRegister | None = Field(
        default=None, description="RED register axis, covered so it cannot be flipped."
    )
    location: RedLocation | None = Field(
        default=None, description="RED location axis, covered so it cannot be flipped."
    )
    inputs_hash: Sha256 = Field(
        description="Hash of the context just evaluated (:func:`context_inputs_hash`)."
    )
    protocol_hash: Sha256 = Field(description="The session's pinned protocol hash.")
    life_threat_version: str = Field(
        min_length=1, description="Version of the base.life_threat sibling set."
    )
    engine_version: str = Field(min_length=1, description="Version of the evaluating engine.")
    issued_at: AwareDatetime = Field(description="When the verdict was signed (files/12 §5: 5 s).")
    nonce: str = Field(
        min_length=2 * NONCE_BYTES,
        max_length=64,
        pattern=r"^[0-9a-f]+$",
        description="Single-use, moves on every attestation.",
    )
    key_id: str = Field(min_length=1, description="Which keyring entry signed this.")

    @model_validator(mode="after")
    def _rule_ids_are_canonical(self) -> TriageClaim:
        if list(self.rule_ids) != sorted(set(self.rule_ids)):
            raise ValueError(
                "rule_ids are sorted and unique (files/12 §5 'sorted rule_ids'), so "
                "the MAC cannot depend on the order a caller happened to pass"
            )
        return self


class TriageAttestation(FrozenModel):
    """A claim and the MAC over it. Travels with the verdict, never alone."""

    claim: TriageClaim
    mac: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
        description="HMAC-SHA256 over the canonical claim, hex.",
    )


# --- canonicalisation --------------------------------------------------------


def _part(value: str) -> bytes:
    """One length-prefixed field.

    Length prefixes rather than a separator: with ``a|b`` there is always a
    second pair of field values that concatenates to the same bytes, and a MAC
    over an ambiguous encoding authenticates the bytes rather than the claim.
    """
    raw = value.encode("utf-8")
    return f"{len(raw)}:".encode("ascii") + raw


def _axis(value: RedRegister | RedLocation | None) -> str:
    """An absent RED axis is the empty string, which the length prefix keeps
    distinct from every present value."""
    return "" if value is None else value.value


def _canonical(claim: TriageClaim) -> bytes:
    return b"".join(
        [
            _DOMAIN,
            _part(claim.session_id),
            _part(claim.ek4.value),
            _part(claim.level.value),
            _part(str(len(claim.rule_ids))),
            *(_part(rule_id) for rule_id in claim.rule_ids),
            _part(_axis(claim.register)),
            _part(_axis(claim.location)),
            _part(claim.inputs_hash),
            _part(claim.protocol_hash),
            _part(claim.life_threat_version),
            _part(claim.engine_version),
            _part(claim.issued_at.astimezone(UTC).isoformat()),
            _part(claim.nonce),
            _part(claim.key_id),
        ]
    )


def _mac(claim: TriageClaim, key: bytes) -> str:
    return hmac.new(key, _canonical(claim), hashlib.sha256).hexdigest()


def context_inputs_hash(context: TriageContext) -> str:
    """files/12 §5's ``inputs_hash``: the context that was just evaluated.

    Binding the verdict to its inputs is what makes a *genuine* RED unusable
    against a later turn of the same session — by then the answers, and so this
    hash, have moved. Slot values render through
    :func:`~protocols.triage.context.render_slot_value`, the same single
    canonicalisation the engine's evidence line uses, so a Decimal keeps its
    authored scale here too (INT-267, invariant 22).
    """
    parts = [_part(context.reference_time.astimezone(UTC).isoformat())]
    for ref in sorted(context.answers):
        answer = context.answers[ref]
        parts.append(_part(ref))
        parts.append(_part(answer.state.value))
        parts.append(_part(str(len(answer.values))))
        parts.extend(_part(render_slot_value(value)) for value in answer.values)
    return hashlib.sha256(b"".join(parts)).hexdigest()


def new_nonce() -> str:
    """A fresh single-use nonce. Moves per attestation; the pack and engine
    versions in the same claim do not."""
    return token_hex(NONCE_BYTES)


class NonceLedger:
    """Nonces already spent, per session.

    Bounded, and safely so: :data:`FRESHNESS_WINDOW` already refuses any
    attestation old enough to have been evicted, so the ledger only has to
    cover what one session can issue inside five seconds.
    """

    def __init__(self, capacity: int = 4096) -> None:
        if capacity < 1:
            raise ValueError("a nonce ledger with no capacity would accept every replay")
        self._capacity = capacity
        self._seen: OrderedDict[tuple[str, str], None] = OrderedDict()

    def remember(self, session_id: str, nonce: str) -> bool:
        """True when the nonce was unseen and is now spent; False on a replay."""
        entry = (session_id, nonce)
        if entry in self._seen:
            return False
        self._seen[entry] = None
        if len(self._seen) > self._capacity:
            self._seen.popitem(last=False)
        return True

    def __len__(self) -> int:
        return len(self._seen)


# --- sign, and verify --------------------------------------------------------


def attest(
    evaluation: TriageEvaluation,
    *,
    session_id: str,
    inputs_hash: str,
    protocol_hash: str,
    life_threat_version: str,
    engine_version: str,
    issued_at: datetime,
    keyring: AttestationKeyring,
    nonce: str | None = None,
    key_id: str | None = None,
) -> TriageAttestation:
    """Sign one evaluation. The rules engine's own capability, and only its.

    Invariant 1 holds by construction: the level, acuity, rule ids and RED axes
    are read off ``evaluation`` — which only
    :func:`~protocols.triage.engine.evaluate_triage` produces — and there is no
    parameter through which a caller could state one.
    """
    result = evaluation.result
    claim = TriageClaim(
        session_id=session_id,
        ek4=evaluation.ek4,
        level=result.level,
        rule_ids=tuple(sorted({fire.id for fire in result.rules})),
        register=result.register,
        location=result.location,
        inputs_hash=inputs_hash,
        protocol_hash=protocol_hash,
        life_threat_version=life_threat_version,
        engine_version=engine_version,
        issued_at=issued_at,
        nonce=new_nonce() if nonce is None else nonce,
        key_id=keyring.active_key_id if key_id is None else key_id,
    )
    return TriageAttestation(claim=claim, mac=_mac(claim, keyring.signing_key(claim.key_id)))


def _refuse(reason: RefusalReason, message: str, tally: ForgedTriageTally | None) -> NoReturn:
    if tally is not None:
        tally.record(reason)
    raise AttestationRefused(reason, message)


def _same_verdict(claim: TriageClaim, result: RulesTriageResult) -> bool:
    return (
        claim.level is result.level
        and claim.rule_ids == tuple(sorted({fire.id for fire in result.rules}))
        and claim.register is result.register
        and claim.location is result.location
    )


def verify(
    attestation: TriageAttestation,
    result: RulesTriageResult,
    *,
    keyring: AttestationKeyring,
    session_id: str,
    inputs_hash: str,
    protocol_hash: str,
    now: datetime,
    nonces: NonceLedger,
    tally: ForgedTriageTally | None = None,
) -> None:
    """Refuse anything that is not this session's freshly-signed verdict.

    Returns ``None`` on success and raises :class:`AttestationRefused`
    otherwise — deliberately not a boolean, because a caller that forgets to
    read a boolean has silently disabled the gate, and deliberately not the
    claim, because handing back a level would make this a second route to one
    (invariant 1). The authenticated fields are already on ``attestation``.
    """
    claim = attestation.claim
    try:
        key = keyring.signing_key(claim.key_id)
    except UnknownKeyId:
        _refuse(RefusalReason.UNKNOWN_KEY, "the attestation names an unknown key id", tally)
    if not hmac.compare_digest(_mac(claim, key), attestation.mac):
        _refuse(RefusalReason.BAD_MAC, "the attestation does not authenticate", tally)
    if not _same_verdict(claim, result):
        _refuse(
            RefusalReason.VERDICT_MISMATCH,
            "the attestation covers a different determination than the one presented",
            tally,
        )
    if not hmac.compare_digest(claim.session_id, session_id):
        _refuse(RefusalReason.SESSION_MISMATCH, "the attestation is for another session", tally)
    if not hmac.compare_digest(claim.inputs_hash, inputs_hash):
        _refuse(
            RefusalReason.INPUTS_MISMATCH,
            "the attestation covers inputs other than the context just evaluated",
            tally,
        )
    if not hmac.compare_digest(claim.protocol_hash, protocol_hash):
        _refuse(
            RefusalReason.PROTOCOL_MISMATCH,
            "the attestation names a pack the session is not pinned to",
            tally,
        )
    if abs(now - claim.issued_at) > FRESHNESS_WINDOW:
        _refuse(
            RefusalReason.STALE,
            f"the attestation is outside the {FRESHNESS_WINDOW.total_seconds():g}s window",
            tally,
        )
    if not nonces.remember(claim.session_id, claim.nonce):
        _refuse(RefusalReason.NONCE_REUSE, "the attestation's nonce is already spent", tally)
