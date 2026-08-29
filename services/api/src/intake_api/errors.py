"""Machine-readable error bodies (INT-197). Every refusal is a flat
``{"error": <code>, ...}`` object — codes, never narrative, so no PHI can
travel in an error (invariant 6) and the mobile app can map codes to its own
tr copy (invariant 5)."""

from __future__ import annotations

from fastapi import HTTPException

__all__ = [
    "age_gate_refused",
    "attestation_invalid",
    "attestation_required",
    "attestation_unverified",
    "challenge_invalid",
    "consent_required",
    "consent_text_changed",
    "consent_text_missing",
    "dev_auth_unconfigured",
    "dpop_invalid",
    "forbidden",
    "not_found",
    "otp_auth_unconfigured",
    "otp_invalid",
    "otp_limited",
    "phone_invalid",
    "purpose_unknown",
    "refresh_reused",
    "taxonomy_unconfigured",
    "unauthorized",
    "visit_invalid",
]


def unauthorized() -> HTTPException:
    return HTTPException(status_code=401, detail={"error": "unauthorized"})


def forbidden() -> HTTPException:
    return HTTPException(status_code=403, detail={"error": "forbidden"})


def consent_required(scope: str) -> HTTPException:
    return HTTPException(status_code=403, detail={"error": "consent_required", "scope": scope})


# --- INT-223 minor & guardian gate -------------------------------------------------------


def age_gate_refused(code: str, scope: str) -> HTTPException:
    """The age/guardian gate refused the scope. ``code`` is the rules
    engine's own refusal code — ``guardian_consent_required``,
    ``dob_unverified`` or ``jurisdiction_unsupported`` — and the body carries
    that plus the scope id and NOTHING else: no date of birth, no age, no
    band, no narrative (invariant 6). The client maps the code to its own tr
    copy (invariant 5)."""
    return HTTPException(status_code=403, detail={"error": code, "scope": scope})


# --- INT-232 consent-management codes (scope is the id and nothing else, invariant 6) ----


def purpose_unknown(scope: str) -> HTTPException:
    """A scope outside the closed files/06 §2 list — including
    ``lane:acoustic`` (an ICF, not a purpose) and the bare ``share`` family
    (a share is always parameterised)."""
    return HTTPException(status_code=422, detail={"error": "purpose_unknown", "scope": scope})


def consent_text_changed(scope: str) -> HTTPException:
    """The submitted {version, text_hash} no longer match the served text:
    the patient granted against a text that has moved — refuse, re-prompt."""
    return HTTPException(status_code=409, detail={"error": "consent_text_changed", "scope": scope})


def consent_text_missing(scope: str) -> HTTPException:
    """No docs/legal text exists for the purpose — no text, no grant
    (invariant 18, matching INT-038's ConsentTextMissingError)."""
    return HTTPException(status_code=409, detail={"error": "text_missing", "scope": scope})


def not_found() -> HTTPException:
    return HTTPException(status_code=404, detail={"error": "not_found"})


def visit_invalid(reason: str) -> HTTPException:
    return HTTPException(status_code=422, detail={"error": reason})


def taxonomy_unconfigured() -> HTTPException:
    """The branch taxonomy failed to load (INT-134): the feed and the
    branch-backed visit path fail CLOSED — an empty branch list rendered by
    a picker would be a lie about coverage; a 503 is the truth."""
    return HTTPException(status_code=503, detail={"error": "taxonomy_unconfigured"})


def dev_auth_unconfigured() -> HTTPException:
    return HTTPException(status_code=503, detail={"error": "dev_auth_unconfigured"})


# --- INT-131 OTP/DPoP auth codes ---------------------------------------------------


def otp_auth_unconfigured() -> HTTPException:
    """OTP auth needs Redis + a tokenization key; without them it fails
    closed while the dev-bearer tier keeps carrying the demo (INT-197)."""
    return HTTPException(status_code=503, detail={"error": "otp_auth_unconfigured"})


def attestation_required() -> HTTPException:
    return HTTPException(status_code=403, detail={"error": "attestation_required"})


def attestation_invalid() -> HTTPException:
    return HTTPException(status_code=403, detail={"error": "attestation_invalid"})


def attestation_unverified() -> HTTPException:
    return HTTPException(status_code=403, detail={"error": "attestation_unverified"})


def challenge_invalid() -> HTTPException:
    return HTTPException(status_code=403, detail={"error": "challenge_invalid"})


def phone_invalid() -> HTTPException:
    return HTTPException(status_code=422, detail={"error": "phone_invalid"})


def otp_limited(retry_after_s: float) -> HTTPException:
    """429 with the generic code (02 §8.2: generic errors, resend limits
    shown) — the dimension that tripped is never disclosed to the caller."""
    return HTTPException(
        status_code=429,
        detail={"error": "otp_limited", "retry_after_s": round(retry_after_s, 1)},
        headers={"Retry-After": str(int(retry_after_s) + 1)},
    )


def otp_invalid() -> HTTPException:
    """One generic refusal for wrong/expired/exhausted codes — the caller
    learns nothing about which (02 §8.2 generic errors)."""
    return HTTPException(status_code=401, detail={"error": "otp_invalid"})


def dpop_invalid(code: str) -> HTTPException:
    return HTTPException(status_code=401, detail={"error": code})


def refresh_reused() -> HTTPException:
    return HTTPException(status_code=401, detail={"error": "refresh_reused"})
