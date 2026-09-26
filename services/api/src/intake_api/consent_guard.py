"""INT-038 — consent_guard: declarative per-route consent scopes.

A route DECLARES the consent scopes it operates under; the guard ENFORCES
the subject-level ones and the route-table scan (tests/legal) fails on any
data route that declares nothing — the acceptance's "every data route
declares scopes". Two declaration slots, because two enforcement shapes
exist in this API:

- ``enforced``: checked here, before the endpoint body, against the
  REQUESTING patient's live consents in a fresh RLS tenant session. A
  clinic-admin principal has no patient row, and the record it touches is
  resolved inside the endpoint — so for non-patient principals the guard
  defers to the route's record-level checks (which call ensure_consent
  below and are therefore staleness-aware too).
- ``conditional``: declared for the scan, enforced inside the endpoint
  where the condition lives (role, record ownership, send-vs-draft). The
  scan sees the full contract either way.

Refusals are a typed 403 naming the missing purpose id and NOTHING else
(invariant 6). A stale grant — the docs/legal text moved since it was
given — is treated as absent and audited as ``consent.stale`` (re-prompt on
change); a plain absence is not audited, because a refused read is not a
read (tests/api/test_visits.py pins that).

**INT-223 — the age/guardian gate runs here too**, not beside it. Before the
ledger is consulted, ``ensure_consent`` resolves the subject's age context
(``intake_api.age_context``) and asks the rules engine
(``intake_platform.consent.minors``) which actor must hold the consent. A
minor's own grant therefore cannot unlock a scope the guardian has to hold,
and there is no second refusal path to keep in step with this one
(invariant 4). The refusal is the engine's own code in a 403 carrying
``{error, scope}`` and nothing derived from the date of birth (invariant 6).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fastapi import Depends, FastAPI, params
from fastapi.routing import APIRoute
from intake_platform.consent import consent_state, resolve_scope
from intake_platform.consent.minors import resolve_consent_actor
from sqlalchemy.ext.asyncio import AsyncSession

from intake_api.auth import Principal
from intake_api.db import tenant_session
from intake_api.errors import age_gate_refused, consent_required
from intake_api.state import State

if TYPE_CHECKING:
    from intake_api.state import ApiState

__all__ = [
    "ADMIN_PREFIX",
    "CONSENT_MANAGEMENT_PREFIX",
    "DATA_SUBJECT_RIGHT_PREFIX",
    "DOCTOR_LINK_PREFIX",
    "META_ROUTES",
    "NOTIFICATION_PREFERENCE_PREFIX",
    "PRE_AUTH_PREFIX",
    "REFERENCE_DATA_PREFIX",
    "ConsentGuard",
    "ConsentPolicy",
    "DEV_VOICE_PREFIX",
    "EMBED_PREFIX",
    "administrative_action",
    "administrative_action_routes",
    "consent_management",
    "consent_management_routes",
    "data_subject_right",
    "data_subject_right_routes",
    "dev_voice_scripted",
    "dev_voice_scripted_routes",
    "doctor_link_redemption",
    "doctor_link_redemption_routes",
    "ensure_age_actor",
    "ensure_consent",
    "notification_preference",
    "notification_preference_routes",
    "partner_embed",
    "partner_embed_routes",
    "pre_auth",
    "pre_auth_routes",
    "reference_data",
    "reference_data_routes",
    "require_scopes",
    "route_policies",
    "unguarded_data_routes",
]

# The invariant-15 service-meta surface plus FastAPI's own schema routes —
# the ONLY paths allowed to carry no consent declaration.
META_ROUTES = frozenset(
    {
        "/healthz",
        "/readyz",
        "/metrics",
        "/version",
        "/openapi.json",
        "/docs",
        "/docs/oauth2-redirect",
        "/redoc",
    }
)


@dataclass(frozen=True)
class ConsentPolicy:
    """One route's declared consent contract."""

    enforced: tuple[str, ...]
    conditional: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.enforced and not self.conditional:
            raise ValueError("a consent policy must declare at least one scope")
        for scope in self.enforced + self.conditional:
            resolve_scope(scope)  # typos and de-listed purposes fail at import


async def ensure_age_actor(
    session: AsyncSession,
    *,
    state: ApiState,
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID,
    scope: str,
) -> None:
    """INT-223 — the age axis of the same enforcement point.

    Refuses when the rules engine says this subject may not be served on the
    age axis at all: an under-18 whose guardian must hold the consent, a date
    of birth that is not verified, a jurisdiction we do not encode. Runs
    BEFORE the ledger so a minor's own grant cannot answer for the guardian's.
    """
    context = await state.age_context.resolve(session, tenant_id=tenant_id, patient_id=patient_id)
    decision = resolve_consent_actor(context, scope=scope, on=datetime.now(UTC).date())
    if decision.permitted:
        return
    # refusal_code is always present on a refusal (the engine sets both
    # together); the fallback keeps the refusal total rather than optional.
    raise age_gate_refused(decision.refusal_code or "guardian_consent_required", scope)


async def ensure_consent(
    session: AsyncSession,
    *,
    state: ApiState,
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID,
    scope: str,
    actor: str,
) -> None:
    """The one enforcement point (invariant 4): route code and the guard
    both come through here, so staleness handling — and, since INT-223, the
    age/guardian gate — cannot fork."""
    await ensure_age_actor(
        session, state=state, tenant_id=tenant_id, patient_id=patient_id, scope=scope
    )
    decision = await consent_state(
        session,
        tenant_id=tenant_id,
        patient_id=patient_id,
        scope=scope,
        catalog=state.consent_catalog,
    )
    if decision.allowed:
        return
    if decision.reason == "stale":
        # the grant exists but binds a superseded text: audit the fact —
        # it is the re-prompt trigger — then refuse exactly like an absence
        await state.audit.record(
            actor=actor,
            action="consent.stale",
            resource_ref=f"patient:{patient_id}",
            consent_scope=f"scope:{scope}",
        )
    raise consent_required(scope)


class ConsentGuard:
    """The dependency a route mounts via require_scopes(...)."""

    def __init__(self, policy: ConsentPolicy) -> None:
        self.policy = policy

    async def __call__(self, principal: Principal, state: State) -> None:
        if principal.patient_id is None:
            return  # record-level checks inside the endpoint cover non-subjects
        async with tenant_session(state.engine, principal.tenant_id) as session:
            for scope in self.policy.enforced:
                await ensure_consent(
                    session,
                    state=state,
                    tenant_id=principal.tenant_id,
                    patient_id=principal.patient_id,
                    scope=scope,
                    actor=principal.account_id,
                )


def require_scopes(*enforced: str, conditional: tuple[str, ...] = ()) -> params.Depends:
    """Declare (and enforce) a route's consent scopes:
    ``dependencies=[require_scopes("core")]`` on the route decorator."""
    dependency: params.Depends = Depends(
        ConsentGuard(ConsentPolicy(tuple(enforced), tuple(conditional)))
    )
    return dependency


class PreAuthDeclaration:
    """Explicit declaration that a route runs BEFORE any principal exists
    (INT-131 onboarding: OTP, attestation, refresh). Consent scopes attach
    to an authenticated subject, so these routes cannot enforce one — but
    they may not stay silent either: the scan accepts this marker ONLY under
    PRE_AUTH_PREFIX, so a data route elsewhere cannot borrow it."""

    async def __call__(self) -> None:
        return


#: The only prefix where a pre-auth declaration is accepted by the scan.
PRE_AUTH_PREFIX = "/v1/auth"


def pre_auth() -> params.Depends:
    """Declare a route as pre-authentication (see PreAuthDeclaration)."""
    dependency: params.Depends = Depends(PreAuthDeclaration())
    return dependency


class ConsentManagementDeclaration:
    """Explicit declaration that a route IS the consent-management surface
    (INT-232): its subject matter is the consent ledger itself, so requiring
    a consent scope would be circular — nobody can need a consent to grant
    their first consent, and a snapshot that 403s on the very staleness it
    exists to report could never trigger a re-prompt. Same class as
    pre_auth: the route cannot enforce a scope, but it may not stay silent
    either — the scan accepts this marker ONLY under
    CONSENT_MANAGEMENT_PREFIX (as a path segment, not a substring), so a
    data route elsewhere cannot borrow it."""

    async def __call__(self) -> None:
        return


#: The only prefix where a consent-management declaration is accepted.
CONSENT_MANAGEMENT_PREFIX = "/v1/consents"


def consent_management() -> params.Depends:
    """Declare a route as consent management (see
    ConsentManagementDeclaration)."""
    dependency: params.Depends = Depends(ConsentManagementDeclaration())
    return dependency


class DataSubjectRightDeclaration:
    """Explicit declaration that a route IS the exercise of a statutory
    data-subject right (INT-037: KVKK m.11 access/rectify/erasure, answered
    within the m.13 window).

    Its lawful basis is legal obligation, not açık rıza, so requiring a
    consent scope here would be a defect rather than a safeguard: the request
    a withdrawal provokes is exactly the request a consent-gated route would
    refuse, and a patient who withdrew ``core`` would find their erasure right
    unreachable. Same class as pre_auth and consent_management — the route
    cannot enforce a scope, but it may not stay silent either, so the scan
    accepts this marker ONLY under DATA_SUBJECT_RIGHT_PREFIX (as a path
    segment, not a substring).

    Access control does not disappear with the scope: these routes are
    patient-only (``require_patient``), act on the requesting subject's own
    rows, and audit every action against the ``basis:KVKK-11/13`` reference.
    """

    async def __call__(self) -> None:
        return


class DoctorLinkRedemptionDeclaration:
    """Explicit declaration that a route IS a Doctor Link redemption
    (INT-150): the caller is a clinician holding a 128-bit token and no
    account, so no principal exists for a route-level guard to resolve.

    The consent scope does NOT disappear with the principal — it moves inside
    the endpoint, which is where the subject can be resolved at all. The token
    names a grant; the grant names a share; the share names the note and its
    patient; and ``ensure_consent`` is then called for
    ``share:previsit_note`` against THAT patient before a single section is
    read (invariant 4). This is the same record-level shape the clinic-admin
    branch of ``notes.read_note`` already uses, and it is enforced by the same
    one evaluator, so a withdrawal or a stale text refuses here too.

    Same class as pre_auth and the other markers: the route cannot enforce a
    scope at the door, but it may not stay silent either — the scan accepts
    this marker ONLY under DOCTOR_LINK_PREFIX (as a path segment, not a
    substring), so a data route elsewhere cannot borrow it.
    """

    async def __call__(self) -> None:
        return


class PartnerEmbedDeclaration:
    """Explicit declaration that a route IS the partner white-label embed
    handshake (INT-320; ADR-028): the caller is a partner backend minting a
    launch ticket, or the patient's device presenting one to start the branded
    intake — in neither case is there a Vizite data subject at the door whose
    consent ledger a scope could be checked against.

    Consent does NOT disappear with the scope, it moves to where the subject
    exists: the launch resolves a tenant's theme and the id of the consent
    document set the patient must be shown, and the patient then grants consent
    through Vizite's own consent flow (``ensure_consent`` against docs/legal,
    hash-bound) BEFORE any clinical turn — the handshake reads and writes no
    clinical data at all. A launch ticket is single-use, short-lived and its
    tenant is bound inside the signature, and every mint and launch is audited.

    Same class as pre_auth and the other markers: the route cannot enforce a
    scope at the door, but it may not stay silent either — the scan accepts this
    marker ONLY under EMBED_PREFIX (as a path segment, not a substring), so a
    /v1 data route cannot borrow it to dodge a scope.
    """

    async def __call__(self) -> None:
        return


class DevVoiceScriptedDeclaration:
    """Explicit declaration that a route is the DEV-lane on-demand synthesis of
    a SCRIPTED question clip in George's voice (ADR-028 on-demand variant,
    ``intake_api.dev_voice``): the body is verbatim scripted ``text_tr`` from a
    compiled pack (invariant 10), never a patient answer and never patient
    audio, and the route reads and writes no clinical data at all.

    Why it cannot carry a consent scope. Same shape as ``partner_embed`` and the
    other markers: the caller is the patient's own device asking for the agent's
    scripted speech, and there is no Vizite data subject whose consent ledger a
    scope could be checked against — files/06 §2's purposes are about a subject's
    clinical data, and no clinical datum is read or written here.

    What it is NOT: a check. This marker only explains the missing scope; the
    route enforces its own doors (INT-326) — a patient principal, a server-side
    catalogue (only a compiled clip-manifest ``text_tr`` is admitted, so the
    scripted-only guarantee no longer rests on the client), a per-principal
    budget, the numeral refusal (invariant 22), and no mount at all in
    production.

    Why it may not stay silent. The scan accepts this marker ONLY under
    DEV_VOICE_PREFIX (as a path segment, not a substring), so a ``/v1`` data
    route cannot borrow it to dodge a scope. The route is dev-gated and fails
    closed (503) when the dev flag, vendor key or compiled catalogue is absent.
    """

    async def __call__(self) -> None:
        return


class ReferenceDataDeclaration:
    """Explicit declaration that a route serves REFERENCE DATA only
    (INT-134): a versioned projection of a committed artefact — the branch
    taxonomy — that contains no patient data at all. Consent scopes attach
    to a data subject's clinical data; demanding one here would over-claim
    (and would block the picker before the patient has granted anything).
    Same class as pre_auth and consent_management: the route cannot enforce
    a scope, but it may not stay silent either — the scan accepts this
    marker ONLY under REFERENCE_DATA_PREFIX (as a path segment, not a
    substring), so a data route elsewhere cannot borrow it. Authentication
    is unchanged: the route still requires a principal."""

    async def __call__(self) -> None:
        return


class AdministrativeActionDeclaration:
    """Explicit declaration that a route is an ADMINISTRATIVE action on the
    control plane (INT-180; files/08 §2, §8), not a read or write of a data
    subject's clinical data.

    Why it cannot carry a consent scope. A console action is taken by a
    member of staff against the platform, and the requesting principal is not
    a patient — there is no data subject whose ledger could be consulted at
    the door. files/06 §2 enumerates the patient's purposes and contains
    nothing covering staff access at all, so any scope named here would be an
    over-claim: it would assert a lawful basis the repository does not have.
    The basis these routes are discharged under is the audit obligation
    itself, recorded on every entry as ``basis:KVKK-12``.

    Why it may not stay silent. An admin action is the most privileged thing
    that happens in this system, so it is audited unconditionally — the
    router is built from the ADMIN_ROUTES descriptor table and every route,
    including every refusal, appends a write-ahead intent row and an outcome
    row to the INT-016 chain. This marker is how that contract is declared to
    the scan; the scan accepts it ONLY under ADMIN_PREFIX (as a path segment,
    not a substring), so a /v1 data route cannot borrow it to dodge a scope.

    The one route that will reach a patient's clinical content — the
    break-glass transcript view of files/08 §2.5 item 5 — is NOT in this
    issue, and it does not get this marker when it lands: §2.5 item 6 puts
    the audit row before the read and invariant 4 puts a consent check with
    it. See files/08 §2.6 and HUMAN_BLOCKERS HB-L6 for the basis that route
    still needs, which is why ``Deployment.CONTROLLER`` refuses today.
    """

    async def __call__(self) -> None:
        return


class NotificationPreferenceDeclaration:
    """Explicit declaration that a route IS the patient's message-refusal
    register (INT-141: opt-out and quiet hours).

    Gate this surface on a consent scope and you build a state in which the
    patient who withdrew ``core`` can no longer reach the switch that stops
    the messages — the same trap the statutory-rights routes documented, and
    the reason 6563's *ret hakkı* has to be exercisable at any time. A
    refusal register that a refusal can lock is not a refusal register. So
    the route cannot enforce a scope; it may not stay silent either, and the
    scan accepts this marker ONLY under NOTIFICATION_PREFERENCE_PREFIX (as a
    path segment, not a substring).

    What does not disappear with the scope: the routes are patient-only
    (``require_patient``), act on the requesting subject's own row, carry no
    clinical data in either direction, and audit every change.
    """

    async def __call__(self) -> None:
        return


#: The only prefix where a data-subject-right declaration is accepted.
DATA_SUBJECT_RIGHT_PREFIX = "/v1/me/dsar"

#: The only prefix where a reference-data declaration is accepted.
REFERENCE_DATA_PREFIX = "/v1/taxonomy"

#: The only prefix where a notification-preference declaration is accepted.
NOTIFICATION_PREFERENCE_PREFIX = "/v1/me/notifications"

#: The only prefix where a Doctor Link redemption declaration is accepted.
DOCTOR_LINK_PREFIX = "/v1/doctor-link"

#: The only prefix where an administrative-action declaration is accepted.
ADMIN_PREFIX = "/admin"

#: The only prefix where a partner-embed declaration is accepted (INT-320).
EMBED_PREFIX = "/embed"

#: The only prefix where a dev-voice scripted declaration is accepted (ADR-028
#: on-demand variant). Dev lane only; the route is absent from every /v1 surface.
DEV_VOICE_PREFIX = "/dev/voice"


def data_subject_right() -> params.Depends:
    """Declare a route as a statutory data-subject right (see
    DataSubjectRightDeclaration)."""
    dependency: params.Depends = Depends(DataSubjectRightDeclaration())
    return dependency


def doctor_link_redemption() -> params.Depends:
    """Declare a route as a Doctor Link redemption (see
    DoctorLinkRedemptionDeclaration)."""
    dependency: params.Depends = Depends(DoctorLinkRedemptionDeclaration())
    return dependency


def reference_data() -> params.Depends:
    """Declare a route as reference data (see ReferenceDataDeclaration)."""
    dependency: params.Depends = Depends(ReferenceDataDeclaration())
    return dependency


def notification_preference() -> params.Depends:
    """Declare a route as the notification-preference register (see
    NotificationPreferenceDeclaration)."""
    dependency: params.Depends = Depends(NotificationPreferenceDeclaration())
    return dependency


def administrative_action() -> params.Depends:
    """Declare a route as an administrative action (see
    AdministrativeActionDeclaration)."""
    dependency: params.Depends = Depends(AdministrativeActionDeclaration())
    return dependency


def partner_embed() -> params.Depends:
    """Declare a route as the partner embed handshake (see
    PartnerEmbedDeclaration)."""
    dependency: params.Depends = Depends(PartnerEmbedDeclaration())
    return dependency


def dev_voice_scripted() -> params.Depends:
    """Declare a route as the dev-lane scripted-clip synthesis (see
    DevVoiceScriptedDeclaration)."""
    dependency: params.Depends = Depends(DevVoiceScriptedDeclaration())
    return dependency


def _policy_of(route: APIRoute) -> ConsentPolicy | None:
    for dependency in route.dependencies:
        call = dependency.dependency
        if isinstance(call, ConsentGuard):
            return call.policy
    return None


def _iter_api_routes(routes: Iterable[object], prefix: str = "") -> Iterator[tuple[str, APIRoute]]:
    """Walk the route table INCLUDING nested routers: FastAPI keeps
    include_router() results as lazy wrapper entries (each holding the
    original router and its include prefix), so a flat scan would miss
    every /v1 route — exactly the routes the scan exists for."""
    for route in routes:
        if isinstance(route, APIRoute):
            yield prefix + route.path, route
            continue
        inner = getattr(route, "original_router", None)
        context = getattr(route, "include_context", None)
        if inner is None and hasattr(route, "routes"):
            inner = route
        if inner is not None:
            child_prefix = prefix + str(getattr(context, "prefix", "") or "")
            inner_routes = getattr(inner, "routes", [])
            yield from _iter_api_routes(list(inner_routes), child_prefix)


def route_policies(app: FastAPI) -> dict[tuple[str, str], ConsentPolicy]:
    """(method, path) → declared policy, for the scan and for review."""
    policies: dict[tuple[str, str], ConsentPolicy] = {}
    for path, route in _iter_api_routes(list(app.routes)):
        policy = _policy_of(route)
        if policy is None:
            continue
        for method in sorted(route.methods or ()):
            policies[(method, path)] = policy
    return policies


def _is_pre_auth(route: APIRoute) -> bool:
    return any(
        isinstance(dependency.dependency, PreAuthDeclaration) for dependency in route.dependencies
    )


def _is_consent_management(route: APIRoute) -> bool:
    return any(
        isinstance(dependency.dependency, ConsentManagementDeclaration)
        for dependency in route.dependencies
    )


def _is_data_subject_right(route: APIRoute) -> bool:
    return any(
        isinstance(dependency.dependency, DataSubjectRightDeclaration)
        for dependency in route.dependencies
    )


def _is_doctor_link_redemption(route: APIRoute) -> bool:
    return any(
        isinstance(dependency.dependency, DoctorLinkRedemptionDeclaration)
        for dependency in route.dependencies
    )


def _is_reference_data(route: APIRoute) -> bool:
    return any(
        isinstance(dependency.dependency, ReferenceDataDeclaration)
        for dependency in route.dependencies
    )


def _is_notification_preference(route: APIRoute) -> bool:
    return any(
        isinstance(dependency.dependency, NotificationPreferenceDeclaration)
        for dependency in route.dependencies
    )


def _is_administrative_action(route: APIRoute) -> bool:
    return any(
        isinstance(dependency.dependency, AdministrativeActionDeclaration)
        for dependency in route.dependencies
    )


def _is_partner_embed(route: APIRoute) -> bool:
    return any(
        isinstance(dependency.dependency, PartnerEmbedDeclaration)
        for dependency in route.dependencies
    )


def _is_dev_voice_scripted(route: APIRoute) -> bool:
    return any(
        isinstance(dependency.dependency, DevVoiceScriptedDeclaration)
        for dependency in route.dependencies
    )


def _under_prefix(path: str, prefix: str) -> bool:
    """Segment-boundary match: the prefix itself and ``<prefix>/...`` qualify;
    a lookalike like ``/v1/consentsish`` does not. Every cage shares this rule,
    so it lives once rather than being re-derived per marker."""
    return path == prefix or path.startswith(prefix + "/")


def _under_consent_management_prefix(path: str) -> bool:
    return _under_prefix(path, CONSENT_MANAGEMENT_PREFIX)


def _under_reference_data_prefix(path: str) -> bool:
    """Segment-boundary match, same rule as the consent-management cage."""
    return _under_prefix(path, REFERENCE_DATA_PREFIX)


def _under_data_subject_right_prefix(path: str) -> bool:
    """Segment-boundary match, same rule as the other cages."""
    return _under_prefix(path, DATA_SUBJECT_RIGHT_PREFIX)


def _under_notification_preference_prefix(path: str) -> bool:
    """Segment-boundary match, same rule as the other cages."""
    return _under_prefix(path, NOTIFICATION_PREFERENCE_PREFIX)


def pre_auth_routes(app: FastAPI) -> list[str]:
    """Every route carrying the pre-auth declaration, for the pin test."""
    marked: list[str] = []
    for path, route in _iter_api_routes(list(app.routes)):
        if _is_pre_auth(route):
            for method in sorted(route.methods or ()):
                marked.append(f"{method} {path}")
    return sorted(marked)


def consent_management_routes(app: FastAPI) -> list[str]:
    """Every route carrying the consent-management declaration, for the pin
    test (INT-232) — reported wherever it appears; whether the scan ACCEPTS
    it is unguarded_data_routes' prefix rule."""
    marked: list[str] = []
    for path, route in _iter_api_routes(list(app.routes)):
        if _is_consent_management(route):
            for method in sorted(route.methods or ()):
                marked.append(f"{method} {path}")
    return sorted(marked)


def data_subject_right_routes(app: FastAPI) -> list[str]:
    """Every route carrying the statutory-right declaration, for the pin test
    (INT-037) — reported wherever it appears; whether the scan ACCEPTS it is
    unguarded_data_routes' prefix rule."""
    marked: list[str] = []
    for path, route in _iter_api_routes(list(app.routes)):
        if _is_data_subject_right(route):
            for method in sorted(route.methods or ()):
                marked.append(f"{method} {path}")
    return sorted(marked)


def doctor_link_redemption_routes(app: FastAPI) -> list[str]:
    """Every route carrying the Doctor Link redemption declaration, for the
    pin test (INT-150) — reported wherever it appears; whether the scan
    ACCEPTS it is unguarded_data_routes' prefix rule."""
    marked: list[str] = []
    for path, route in _iter_api_routes(list(app.routes)):
        if _is_doctor_link_redemption(route):
            for method in sorted(route.methods or ()):
                marked.append(f"{method} {path}")
    return sorted(marked)


def reference_data_routes(app: FastAPI) -> list[str]:
    """Every route carrying the reference-data declaration, for the pin
    test (INT-134) — reported wherever it appears; whether the scan ACCEPTS
    it is unguarded_data_routes' prefix rule."""
    marked: list[str] = []
    for path, route in _iter_api_routes(list(app.routes)):
        if _is_reference_data(route):
            for method in sorted(route.methods or ()):
                marked.append(f"{method} {path}")
    return sorted(marked)


def notification_preference_routes(app: FastAPI) -> list[str]:
    """Every route carrying the notification-preference declaration, for the
    pin test (INT-141) — reported wherever it appears; whether the scan
    ACCEPTS it is unguarded_data_routes' prefix rule."""
    marked: list[str] = []
    for path, route in _iter_api_routes(list(app.routes)):
        if _is_notification_preference(route):
            for method in sorted(route.methods or ()):
                marked.append(f"{method} {path}")
    return sorted(marked)


def administrative_action_routes(app: FastAPI) -> list[str]:
    """Every route carrying the administrative-action declaration, for the
    pin test (INT-180) — reported wherever it appears; whether the scan
    ACCEPTS it is unguarded_data_routes' prefix rule."""
    marked: list[str] = []
    for path, route in _iter_api_routes(list(app.routes)):
        if _is_administrative_action(route):
            for method in sorted(route.methods or ()):
                marked.append(f"{method} {path}")
    return sorted(marked)


def partner_embed_routes(app: FastAPI) -> list[str]:
    """Every route carrying the partner-embed declaration, for the pin test
    (INT-320) — reported wherever it appears; whether the scan ACCEPTS it is
    unguarded_data_routes' prefix rule."""
    marked: list[str] = []
    for path, route in _iter_api_routes(list(app.routes)):
        if _is_partner_embed(route):
            for method in sorted(route.methods or ()):
                marked.append(f"{method} {path}")
    return sorted(marked)


def dev_voice_scripted_routes(app: FastAPI) -> list[str]:
    """Every route carrying the dev-voice scripted declaration, for the pin test
    (ADR-028 on-demand) — reported wherever it appears; whether the scan ACCEPTS
    it is unguarded_data_routes' prefix rule."""
    marked: list[str] = []
    for path, route in _iter_api_routes(list(app.routes)):
        if _is_dev_voice_scripted(route):
            for method in sorted(route.methods or ()):
                marked.append(f"{method} {path}")
    return sorted(marked)


def unguarded_data_routes(app: FastAPI) -> list[str]:
    """Every data route that declares neither consent scopes nor a valid
    marker — the scan test asserts this list is empty, so a new route cannot
    land undeclared (silence always fails). Seven markers exist, each caged to
    its prefix: pre_auth under PRE_AUTH_PREFIX (INT-131 bootstrap, no
    principal yet), consent_management under CONSENT_MANAGEMENT_PREFIX
    (INT-232, the routes ABOUT consent), reference_data under
    REFERENCE_DATA_PREFIX (INT-134, versioned artefact projections holding no
    patient data), data_subject_right under DATA_SUBJECT_RIGHT_PREFIX
    (INT-037, the statutory rights whose basis is legal obligation rather than
    consent) and notification_preference under NOTIFICATION_PREFERENCE_PREFIX
    (INT-141, the message-refusal register a withdrawal must not lock) and
    doctor_link_redemption under DOCTOR_LINK_PREFIX (INT-150, the clinician
    holding a token and no account, whose consent check runs record-level
    inside the endpoint) and administrative_action under ADMIN_PREFIX
    (INT-180, a staff action on the control plane with no data subject at the
    door, discharged under the audit obligation and audited unconditionally)
    and partner_embed under EMBED_PREFIX (INT-320, the white-label handshake
    that mints and launches a signed ticket before any Vizite subject exists
    and reads no clinical data) and dev_voice_scripted under DEV_VOICE_PREFIX
    (ADR-028 on-demand variant, the dev-lane synthesis of a verbatim scripted
    question clip that reads no clinical data and never touches patient audio).
    Any marker outside its prefix does NOT count as a declaration (the route is
    reported here instead)."""
    missing: list[str] = []
    for path, route in _iter_api_routes(list(app.routes)):
        if path in META_ROUTES:
            continue
        if _is_pre_auth(route) and _under_prefix(path, PRE_AUTH_PREFIX):
            continue
        if _is_consent_management(route) and _under_consent_management_prefix(path):
            continue
        if _is_reference_data(route) and _under_reference_data_prefix(path):
            continue
        if _is_data_subject_right(route) and _under_data_subject_right_prefix(path):
            continue
        if _is_notification_preference(route) and _under_notification_preference_prefix(path):
            continue
        if _is_doctor_link_redemption(route) and _under_prefix(path, DOCTOR_LINK_PREFIX):
            continue
        if _is_administrative_action(route) and _under_prefix(path, ADMIN_PREFIX):
            continue
        if _is_partner_embed(route) and _under_prefix(path, EMBED_PREFIX):
            continue
        if _is_dev_voice_scripted(route) and _under_prefix(path, DEV_VOICE_PREFIX):
            continue
        if _policy_of(route) is None:
            for method in sorted(route.methods or ()):
                missing.append(f"{method} {path}")
    return missing
