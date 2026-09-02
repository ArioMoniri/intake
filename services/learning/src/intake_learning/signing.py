"""INT-172 — signing a proposal and its evidence (files/09 §7; files/10 §9).

files/09 §7: "proposals and evidence bundles are signed". files/10 §9's
learning row lists "evidence signed" among the controls.

**Which signature, and why not a new one.** This repository has already chosen
its primitives twice, and both choices are HMAC-SHA256 with the key held in
OpenBao: ``intake_platform.room_tokens`` mints LiveKit tokens that way with
nothing but stdlib ``hmac``, and files/12 §5 specifies the rules-engine
attestation over ``(session_id, ek4, disposition, rule_ids, inputs_hash,
protocol_hash, …)`` the same way — that one lands with INT-093 and is
deliberately not duplicated here. ``cosign`` appears in CLAUDE.md and
ADR-017 for **images and protocol bundles**, which are release artefacts with a
build-time identity; a weekly job's output is neither. So this is HMAC-SHA256
over the canonical bundle digest, and there is no third scheme in the tree.

**The canonical form is the audit chain's.** ``json.dumps(..., sort_keys=True,
separators=(",", ":"), ensure_ascii=True)``, byte for byte what
``intake_platform.audit._entry_hash`` uses, for the reason its docstring
gives: "the format is deliberately boring and fully specified so an
independent implementation reproduces it byte for byte". A clinician's
reviewer should be able to re-derive the digest without this package.

**The key is handed in, never fetched.** :func:`sign_bundle` takes bytes. This
package holds no secrets client and no HTTP client at all — the
``proposal_scope`` gate asserts that the pipeline's import closure reaches
neither — so "sandboxed job … no egress" (files/09 §7) is a property of the
source rather than of a container policy. Where the key comes from is the
deployment's problem, and an absent key fails closed here rather than
producing an unsigned bundle that looks signed.

sec_row: `learning-loops`.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Final

from intake_learning.evidence import EvidenceBundle

__all__ = [
    "SIGNATURE_ALGORITHM",
    "Signature",
    "SignedBundle",
    "SigningKeyUnavailable",
    "digest_of",
    "sign_bundle",
    "verify_bundle",
]

SIGNATURE_ALGORITHM: Final = "hmac-sha256"

#: Shorter than this is not a key. 32 bytes is the SHA-256 block-appropriate
#: floor the repository's other HMAC users assume; a truncated or stand-in key
#: is refused rather than used.
_MIN_KEY_BYTES: Final = 32


class SigningKeyUnavailable(RuntimeError):
    """No usable signing key. Nothing is emitted; the run fails closed.

    An unsigned bundle that still opened a PR would be worse than no PR: the
    reviewing clinician's only assurance that the numbers came from the
    sandboxed job is the signature.
    """


@dataclass(frozen=True)
class Signature:
    key_id: str
    algorithm: str
    value: str


@dataclass(frozen=True)
class SignedBundle:
    """An evidence bundle, its digest, and a detached MAC over that digest."""

    bundle: EvidenceBundle
    digest: str
    signature: Signature

    @property
    def is_complete(self) -> bool:
        return self.bundle.is_complete

    @property
    def unmet_checks(self) -> tuple[str, ...]:
        return self.bundle.unmet_checks


def digest_of(bundle: EvidenceBundle) -> str:
    """SHA-256 over the bundle's canonical serialisation."""
    return hashlib.sha256(bundle.to_json().encode("utf-8")).hexdigest()


def sign_bundle(bundle: EvidenceBundle, *, key: bytes, key_id: str) -> SignedBundle:
    """Detached HMAC-SHA256 over :func:`digest_of`.

    :raises SigningKeyUnavailable: the key is absent or too short, or the key
        id is empty — a signature nobody can attribute is not evidence.
    """
    if len(key) < _MIN_KEY_BYTES:
        raise SigningKeyUnavailable(
            f"a proposal signing key must be at least {_MIN_KEY_BYTES} bytes; "
            "the run fails closed rather than emitting an unsigned bundle "
            "(files/09 §7). The key value is deliberately not echoed"
        )
    if not key_id.strip():
        raise SigningKeyUnavailable(
            "a signature needs a key id: a reviewer must be able to say which "
            "key attested the bundle"
        )
    digest = digest_of(bundle)
    mac = hmac.new(key, digest.encode("ascii"), hashlib.sha256).hexdigest()
    return SignedBundle(
        bundle=bundle,
        digest=digest,
        signature=Signature(key_id=key_id, algorithm=SIGNATURE_ALGORITHM, value=mac),
    )


def verify_bundle(signed: SignedBundle, *, key: bytes) -> bool:
    """True when the MAC covers the digest **and** the digest covers the bundle.

    Both halves matter: checking only the MAC would accept a bundle whose
    contents were swapped under a digest that still verifies.
    """
    if signed.signature.algorithm != SIGNATURE_ALGORITHM:
        return False
    if digest_of(signed.bundle) != signed.digest:
        return False
    expected = hmac.new(key, signed.digest.encode("ascii"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signed.signature.value)
