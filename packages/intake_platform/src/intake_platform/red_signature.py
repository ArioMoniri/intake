"""The synthetic-only test-key signature over the red rule set (INT-465).

**What it is for.** Owner decision, 3 Oct 2026, read with D18 (agent-only clinical
sign-off for simulated-patient testing): the red rule set served on the synthetic AWS
test host is signed with a test key. On that host the signature stands in for the
physician's sign-off (HB-C1). That is safe only because no real patient is ever there.

**Where the key is.** It is an ed25519 key in OpenBao Transit on that host
(i-0e489e48739f5de98), created non-exportable. Its private half never leaves OpenBao,
so it is in no repository and no log. ``infra/staging/redset_signer.sh`` is the only
thing that signs with it, through a token whose policy allows ``sign`` on that key
alone. The public half is committed in :data:`COMMITTED_TRUST_REGISTRY`.

**What it binds.** The canonical bytes of one :class:`RedRuleSetPayload`:
- the sha256 of the life-threat set's bytes;
- the sha256 of the generic RED document's bytes;
- the exact sorted list of rule ids served (only ``active`` rules; a draft rule is
  never served);
- the scope the signature was made for.
A changed byte, a dropped or added rule, or a payload edited after signing is refused.

**Who may accept it.** A tenant admits a key scope only through
:func:`admitted_scopes`, an allow-list keyed on :attr:`TenantKind.SYNTHETIC` alone. So
**any non-synthetic tenant config rejects the test-key signature**, including a tenant
kind added later. The tenant check runs before any cryptography: a real tenant never
evaluates a test signature at all.

**What it is not.** It is not the production signing path. That path is cosign keyless
signing of protocol bundles in CI (INT-058; files/10 §8), and it is untouched here. This
registry can never hold a production key: :class:`KeyScope` has the one member. It fills
no ``clinical_signoff`` field and flips no ``served`` flag (D17 stands). It closes no
HUMAN_BLOCKERS row.
"""

from __future__ import annotations

import base64
import binascii
import enum
import hashlib
import json
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from clinical_schemas.common import FrozenModel
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import Field, ValidationError, field_validator

from intake_platform.red_tenant import TenantKind, TenantRedConfig

__all__ = [
    "AUTHORITY",
    "COMMITTED_SIGNATURE",
    "COMMITTED_TRUST_REGISTRY",
    "PAYLOAD_KIND",
    "KeyScope",
    "RedRuleSetPayload",
    "RedRuleSetSignature",
    "RedSignatureRefused",
    "SignedFile",
    "TrustRegistry",
    "TrustedKey",
    "admitted_scopes",
    "canonical_payload_bytes",
    "load_signature",
    "load_trust_registry",
    "verify_red_rule_set",
]

# The signed artefacts live with the protocols they sign (packages/protocols/signing).
# An editable install resolves this under the repository, as in the API image (/app).
_SIGNING_DIR = Path(__file__).resolve().parents[4] / "packages" / "protocols" / "signing"
COMMITTED_TRUST_REGISTRY = _SIGNING_DIR / "trusted_keys.yaml"
COMMITTED_SIGNATURE = _SIGNING_DIR / "red_rule_set.synthetic.json"

PAYLOAD_KIND: Literal["intake.red_rule_set.v1"] = "intake.red_rule_set.v1"
AUTHORITY = (
    "D18 (2 Oct 2026) and the owner's decision of 3 Oct 2026: a test key signs the red "
    "rule set for the synthetic AWS test host only. A licensed physician's review is "
    "required before any real patient."
)

_ED25519_PUBLIC_BYTES = 32
_ED25519_SIGNATURE_BYTES = 64


class KeyScope(enum.StrEnum):
    """What a key may sign for. The one member is the test scope; a production key
    belongs to the cosign path (INT-058) and is never registered here."""

    SYNTHETIC_TEST = "synthetic_test"


class RedSignatureRefused(ValueError):
    """The red rule set's signature cannot be trusted for this tenant.

    ``code`` is a closed, id-shaped reason. It names no key material and no rule
    content, so it may be logged (invariant 6).
    """

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _b64(value: str, length: int, what: str) -> bytes:
    try:
        raw = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(f"{what} is not base64") from exc
    if len(raw) != length:
        raise ValueError(f"{what} is {len(raw)} bytes, not {length}")
    return raw


class TrustedKey(FrozenModel):
    """The public half of one signing key, and where its private half is held."""

    key_id: str = Field(
        pattern=r"^[a-z0-9][a-z0-9-]*@[1-9][0-9]*$",
        description="<transit key name>@<version>.",
    )
    algorithm: Literal["ed25519"] = Field(description="Signature algorithm.")
    public_key: str = Field(description="Raw 32-byte ed25519 public key, base64.")
    scope: KeyScope = Field(description="What the key may sign for.")
    custody: str = Field(min_length=1, description="Where the private half lives.")
    created_on: date = Field(description="When the key was created.")

    @field_validator("public_key")
    @classmethod
    def _is_an_ed25519_public_key(cls, value: str) -> str:
        _b64(value, _ED25519_PUBLIC_BYTES, "public_key")
        return value


class TrustRegistry(FrozenModel):
    """``packages/protocols/signing/trusted_keys.yaml``: public keys only."""

    kind: Literal["red_rule_set_trusted_keys"] = Field(description="Document kind.")
    keys: tuple[TrustedKey, ...] = Field(min_length=1, description="The trusted keys.")

    @field_validator("keys")
    @classmethod
    def _ids_are_unique(cls, value: tuple[TrustedKey, ...]) -> tuple[TrustedKey, ...]:
        ids = [key.key_id for key in value]
        if len(ids) != len(set(ids)):
            raise ValueError("a key id appears twice")
        return value

    def key(self, key_id: str) -> TrustedKey | None:
        return next((key for key in self.keys if key.key_id == key_id), None)


class SignedFile(FrozenModel):
    """One signed document: its repo-relative path (informational) and its digest."""

    path: str = Field(min_length=1, description="Repo-relative path when signed.")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$", description="sha256 of its exact bytes.")


class RedRuleSetPayload(FrozenModel):
    """Exactly what the signature covers."""

    kind: Literal["intake.red_rule_set.v1"] = Field(description="Payload kind.")
    scope: KeyScope = Field(description="What it was signed for; must be its key's scope.")
    authority: str = Field(min_length=1, description="The decision that permits the signature.")
    life_threat: SignedFile = Field(description="The life-threat set.")
    generic_red: SignedFile = Field(description="The generic RED document.")
    served_rule_ids: tuple[str, ...] = Field(
        min_length=1, description="The rule ids served: active rules only, sorted, unique."
    )

    @field_validator("served_rule_ids")
    @classmethod
    def _sorted_and_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if list(value) != sorted(set(value)):
            raise ValueError("served_rule_ids are sorted and unique")
        return value

    @classmethod
    def build(
        cls,
        *,
        scope: KeyScope,
        life_threat_path: str,
        life_threat_bytes: bytes,
        generic_red_path: str,
        generic_red_bytes: bytes,
        served_rule_ids: Sequence[str],
    ) -> RedRuleSetPayload:
        return cls(
            kind=PAYLOAD_KIND,
            scope=scope,
            authority=AUTHORITY,
            life_threat=SignedFile(
                path=life_threat_path, sha256=hashlib.sha256(life_threat_bytes).hexdigest()
            ),
            generic_red=SignedFile(
                path=generic_red_path, sha256=hashlib.sha256(generic_red_bytes).hexdigest()
            ),
            served_rule_ids=tuple(sorted(set(served_rule_ids))),
        )


class RedRuleSetSignature(FrozenModel):
    """The committed envelope: the payload, the key that signed it, the signature."""

    payload: RedRuleSetPayload = Field(description="What is signed.")
    key_id: str = Field(min_length=1, description="The registry key that signed it.")
    signature: str = Field(description="Raw 64-byte ed25519 signature, base64.")

    @field_validator("signature")
    @classmethod
    def _is_an_ed25519_signature(cls, value: str) -> str:
        _b64(value, _ED25519_SIGNATURE_BYTES, "signature")
        return value


def canonical_payload_bytes(payload: RedRuleSetPayload) -> bytes:
    """The bytes that are signed: sorted keys, no whitespace, UTF-8."""
    return json.dumps(
        payload.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def admitted_scopes(tenant: TenantRedConfig) -> frozenset[KeyScope]:
    """The key scopes this tenant trusts. An allow-list: synthetic admits the test
    scope, and every other kind, including one added later, admits nothing."""
    if tenant.kind is TenantKind.SYNTHETIC:
        return frozenset({KeyScope.SYNTHETIC_TEST})
    return frozenset()


def verify_red_rule_set(
    signature: RedRuleSetSignature,
    *,
    registry: TrustRegistry,
    tenant: TenantRedConfig,
    life_threat_bytes: bytes,
    generic_red_bytes: bytes,
    served_rule_ids: Sequence[str],
) -> TrustedKey:
    """The key that signed exactly these bytes and rules, trusted by this tenant.

    Raises :class:`RedSignatureRefused` otherwise.
    """
    key = registry.key(signature.key_id)
    if key is None:
        raise RedSignatureRefused("unknown_key")
    if key.scope not in admitted_scopes(tenant):
        raise RedSignatureRefused("key_scope_not_admitted_for_tenant")
    payload = signature.payload
    if payload.scope is not key.scope:
        raise RedSignatureRefused("payload_scope_mismatch")
    public = Ed25519PublicKey.from_public_bytes(base64.b64decode(key.public_key))
    try:
        public.verify(base64.b64decode(signature.signature), canonical_payload_bytes(payload))
    except InvalidSignature as exc:
        raise RedSignatureRefused("bad_signature") from exc
    if hashlib.sha256(life_threat_bytes).hexdigest() != payload.life_threat.sha256:
        raise RedSignatureRefused("life_threat_digest_mismatch")
    if hashlib.sha256(generic_red_bytes).hexdigest() != payload.generic_red.sha256:
        raise RedSignatureRefused("generic_red_digest_mismatch")
    if tuple(sorted(set(served_rule_ids))) != payload.served_rule_ids or len(
        set(served_rule_ids)
    ) != len(served_rule_ids):
        raise RedSignatureRefused("served_rules_mismatch")
    return key


def load_trust_registry(path: Path) -> TrustRegistry:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        return TrustRegistry.model_validate(raw)
    except (OSError, UnicodeDecodeError, yaml.YAMLError, ValidationError) as exc:
        raise RedSignatureRefused("malformed_trust_registry") from exc


def load_signature(path: Path) -> RedRuleSetSignature:
    try:
        return RedRuleSetSignature.model_validate_json(path.read_bytes())
    except (OSError, UnicodeDecodeError, ValidationError) as exc:
        raise RedSignatureRefused("malformed_signature") from exc
