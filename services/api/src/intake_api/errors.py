"""Machine-readable error bodies (INT-197). Every refusal is a flat
``{"error": <code>, ...}`` object — codes, never narrative, so no PHI can
travel in an error (invariant 6) and the mobile app can map codes to its own
tr copy (invariant 5)."""

from __future__ import annotations

from fastapi import HTTPException

__all__ = [
    "admin_console_unconfigured",
    "admin_refused",
    "benchmark_refused",
    "age_gate_refused",
    "break_glass_refused",
    "four_eyes_refused",
    "source_ip_refused",
    "proxy_acknowledgement_required",
    "attestation_invalid",
    "attestation_required",
    "attestation_unverified",
    "challenge_invalid",
    "consent_required",
    "consent_text_changed",
    "consent_text_missing",
    "dev_auth_unconfigured",
    "doctor_link_expired",
    "doctor_link_revoked",
    "doctor_link_unconfigured",
    "doctor_link_view_limit",
    "note_not_shared",
    "dpop_invalid",
    "forbidden",
    "invalid_window",
    "not_found",
    "otp_auth_unconfigured",
    "otp_invalid",
    "otp_limited",
    "phone_invalid",
    "previsit_output_recipient_unregistered",
    "previsit_output_unconfigured",
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


# --- INT-133 companion / proxy flow -------------------------------------------------------


def proxy_acknowledgement_required() -> HTTPException:
    """A companion declared the role but has not acknowledged answering on
    the patient's behalf (files/06 §6). A bare code: the body says what is
    missing and nothing about the subject or the companion (invariant 6).

    This is NOT the guardian path. Acknowledging the role proves no legal
    representation — the proof standard is the awaiting-human
    ``guardian_relationship_proof`` policy row — and a minor subject is
    refused by the age gate long before this code can be reached.
    """
    return HTTPException(status_code=422, detail={"error": "proxy_acknowledgement_required"})


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


# --- the previsit-output read-back (owner directive) ------------------------------------


def previsit_output_recipient_unregistered() -> HTTPException:
    """No approved reader answers for this tenant.

    503 rather than 403 because this is a statement about the SERVICE, not
    about the caller: no DPA is executed and no tier-3 approval exists, so the
    interface is not configured to serve anybody. The body says nothing about
    which tenants do have a row (infra/previsit_output/recipients.yaml).
    """
    return HTTPException(
        status_code=503, detail={"error": "previsit_output_recipient_unregistered"}
    )


def previsit_output_unconfigured() -> HTTPException:
    """No tokenization key, so a hospital patient number cannot be resolved to
    the pseudonym that addresses a patient (invariant 14). Fail closed — a
    scan of every patient row is not the fallback."""
    return HTTPException(status_code=503, detail={"error": "previsit_output_unconfigured"})


def not_found() -> HTTPException:
    return HTTPException(status_code=404, detail={"error": "not_found"})


def visit_invalid(reason: str) -> HTTPException:
    return HTTPException(status_code=422, detail={"error": reason})


def invalid_window(reason: str) -> HTTPException:
    """INT-241: a measurement window that is not a forward instant range.

    ``Cohort`` owns the rule (invariant 20 — a figure without a window is not
    a measurement); this turns its refusal into a 422 carrying the reason
    text, which names bounds and never data.
    """
    return HTTPException(status_code=422, detail={"error": "invalid_window", "reason": reason})


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


# --- INT-150 Doctor Link codes (ids and codes only, invariant 6) ------------------


def doctor_link_unconfigured() -> HTTPException:
    """The Doctor Link tier needs the same Redis the OTP tier needs (the code,
    its attempt budget and its request windows all live in that one gate).
    Without it the whole surface answers 503 rather than issuing links whose
    OTP nobody can check."""
    return HTTPException(status_code=503, detail={"error": "doctor_link_unconfigured"})


def note_not_shared() -> HTTPException:
    """A link was asked for over a note the patient has not sent. There is no
    grant to attach it to, so there is nothing to tokenize (invariant 4)."""
    return HTTPException(status_code=409, detail={"error": "note_not_shared"})


def doctor_link_expired() -> HTTPException:
    """Past ``visit_datetime + 72 h`` (files/02 §2b).

    The reason is stated rather than hidden behind a generic refusal, and only
    to a caller who already presented the 128-bit token: telling the holder of
    a valid-but-finished link WHY it stopped is what turns "the doctor
    couldn't see it" into "ask the patient to send a new one". A caller
    without the token gets ``not_found`` and learns nothing.
    """
    return HTTPException(status_code=410, detail={"error": "doctor_link_expired"})


def doctor_link_revoked() -> HTTPException:
    return HTTPException(status_code=410, detail={"error": "doctor_link_revoked"})


def doctor_link_view_limit() -> HTTPException:
    return HTTPException(status_code=403, detail={"error": "doctor_link_view_limit"})


# --- INT-180 admin console (files/08 §2, §8) ----------------------------------------------


def admin_console_unconfigured() -> HTTPException:
    """No OIDC claims verifier is wired, so the console authenticates nobody.

    Validating a Keycloak assertion needs a JWKS client and a JWT library,
    neither of which is a dependency of this repository, and hand-rolling JWS
    verification inside the highest-privilege surface in the system is not a
    trade INT-180 was willing to make. The seam is
    ``intake_platform.admin.AdminClaimsVerifier``; until one is wired every
    ``/admin`` route answers 503 rather than admitting anyone.
    """
    return HTTPException(status_code=503, detail={"error": "admin_console_unconfigured"})


def source_ip_refused() -> HTTPException:
    """files/08 §2.3's console IP allow-list. Empty admits nobody, which is
    the correct shipping state — no file in this repository names a range."""
    return HTTPException(status_code=403, detail={"error": "source_ip_refused"})


def admin_refused(code: str) -> HTTPException:
    """A refusal from the console's own guards — role, tenant scope, or a
    malformed claim set. ``code`` is machine-shaped and carries no narrative
    and no claim value (invariant 6)."""
    return HTTPException(status_code=403, detail={"error": code})


def four_eyes_refused(code: str) -> HTTPException:
    """A ceremony refusal (files/08 §8.2). 409: the request was understood
    and the ceremony's state or distinctness rule forbids it."""
    return HTTPException(status_code=409, detail={"error": code})


def benchmark_refused(code: str, reason: str) -> HTTPException:
    """INT-183: the models module refused to plan a benchmark. 409 — the
    request was understood and cannot honestly be answered: an unknown
    component, an unexpected field, or (today, for every quality request) no
    named evaluation corpus to measure over. ``reason`` is static operator
    text: it names an invariant and a blocker id, never a value from the
    request and never anything patient-shaped (invariant 6)."""
    return HTTPException(status_code=409, detail={"error": code, "reason": reason})


def break_glass_refused(code: str) -> HTTPException:
    """A §2.5 content-rule refusal — the reason class, the free-text floor,
    the controller-instruction reference, or the absent lawful basis."""
    return HTTPException(status_code=422, detail={"error": code})
