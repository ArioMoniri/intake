"""Staff second factor (INT-365; files/08 §2.3; sec_row admin-console).

files/08 §2.3 makes MFA mandatory for every console role and phishing-resistant
WebAuthn mandatory for anything touching patient content. TOTP is phishable,
and a phished ``platform_owner`` plus a phished approver is a device-mode flip.

**Which roles need WebAuthn is derived, never listed.** A role needs it when
its files/08 §2.1 "may reach patient content?" cell is anything but "no", which
:mod:`intake_platform.admin.roles` already carries as
:class:`~intake_platform.admin.roles.PatientContentPath`. A role added to §2.1
therefore lands on the correct side by construction.

**The evidence is the ``amr`` claim, and only that claim.** RFC 8176 gives the
values. Keycloak emits none by default. Its ``oidc-amr-mapper`` writes the
``default.reference.value`` configured on each authenticator execution the
user completed within that execution's ``default.reference.maxAge``, and
nothing for an execution without one (Keycloak ``AmrUtils``). The committed
realm tags the password form ``pwd``, the OTP form ``otp`` and the WebAuthn
authenticator ``hwk`` ("proof-of-possession of a hardware-secured key"). The
constants below and that realm are held in lockstep by
``tests/admin/test_staff_second_factor.py``.

**``acr`` is never evidence.** Without a step-up LoA flow, Keycloak's ``acr``
is ``"1"`` for a fresh login and ``"0"`` for a cookie one. That records when
the login happened, not how. A token whose ``acr`` names a level and whose
``amr`` shows nothing is refused.

**The claim's shape is not negotiable.** OIDC Core §2 defines ``amr`` as a JSON
array of case-sensitive strings. A bare string, a mapping, or a list with a
member that is not a string is treated as no evidence at all. Nothing is
split, filtered or case-folded: a lenient parser is how ``"hwk"`` gets found
inside something that is not a list of methods. An absent claim fails closed.
"""

from __future__ import annotations

from collections.abc import Iterable

from intake_platform.admin.roles import AdminRole, PatientContentPath, role_spec

__all__ = [
    "AMR_FIRST_FACTOR",
    "AMR_OTP",
    "AMR_WEBAUTHN",
    "PHISHING_RESISTANT_FACTORS",
    "SECOND_FACTORS",
    "SecondFactorRequired",
    "accepted_second_factors",
    "authentication_methods",
    "require_second_factor",
    "requires_webauthn",
]

#: RFC 8176 values, as the committed realm tags its executions. The first
#: factor is the password form's reference.
AMR_FIRST_FACTOR = "pwd"
AMR_OTP = "otp"
AMR_WEBAUTHN = "hwk"

SECOND_FACTORS: frozenset[str] = frozenset({AMR_OTP, AMR_WEBAUTHN})
PHISHING_RESISTANT_FACTORS: frozenset[str] = frozenset({AMR_WEBAUTHN})


class SecondFactorRequired(Exception):
    """The token does not show the factors the caller's console roles need.

    RFC 9470 answers this with 401 ``insufficient_user_authentication``, and
    ``code`` is that value. It is one code for "no second factor" and for
    "not WebAuthn", so the answer does not reveal whether an account reaches
    patient content. ``subject`` is carried so the audit row can name the
    caller. It is set only when the verified ``sub`` is id-shaped, and nothing
    else from the claim set travels (invariant 6).
    """

    code = "insufficient_user_authentication"

    def __init__(self, subject: str | None) -> None:
        super().__init__("the token does not show the second factor its console roles require")
        self.subject = subject


def requires_webauthn(role: AdminRole) -> bool:
    """files/08 §2.3: WebAuthn for any role that reaches patient content."""
    return role_spec(role).patient_content is not PatientContentPath.NONE


def accepted_second_factors(roles: Iterable[AdminRole]) -> frozenset[str]:
    """The ``amr`` values that satisfy the second factor for this role set.
    The strongest requirement across the held roles wins."""
    if any(requires_webauthn(role) for role in roles):
        return PHISHING_RESISTANT_FACTORS
    return SECOND_FACTORS


def authentication_methods(amr: object) -> frozenset[str] | None:
    """The claim as a set of method values, or ``None`` when its shape is not
    a JSON array of strings."""
    if not isinstance(amr, list):
        return None
    if not all(isinstance(method, str) for method in amr):
        return None
    return frozenset(amr)


def require_second_factor(amr: object, roles: frozenset[AdminRole], *, subject: str | None) -> None:
    """Refuse unless ``amr`` shows the password and a second factor these
    roles accept."""
    methods = authentication_methods(amr)
    if (
        methods is None
        or AMR_FIRST_FACTOR not in methods
        or not methods & accepted_second_factors(roles)
    ):
        raise SecondFactorRequired(subject)
