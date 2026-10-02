# ADR-029 · Embeddable white-label integration: a signed launch-ticket handshake, not an embedded UI

Status: Accepted

## Context

Önvizit has to be presentable as a service a partner (a hospital group, a clinic
platform) drops into its own app "as a button": the patient taps *Start
pre-visit*, the Önvizit intake runs branded for that partner, and the clinician
note flows back. The tempting shape — a web component or SDK that renders the
Önvizit intake UI inside the partner's page/origin — is the wrong one for this
product: it puts a PHI surface inside a third-party origin (the exact
"no PHI store reachable from a browser origin" hazard the admin-console threat
model names), it makes the partner's page an injection surface into a Class IIb
device-adjacent flow, and it multiplies the consent, audit and residency
questions across origins we do not control. Meanwhile every isolation invariant
this repo holds is on the path at once: tenant isolation (inv. 14, inv. 37 —
RLS protects the row, not a request parameter), consent + audit on every
read/share (inv. 4), no PHI in logs (inv. 6), consent/legal texts only from
docs/legal with hash binding (inv. 18), `device_functions` off without a CE
certificate (ADR-020), and secrets only from OpenBao (inv. 14). Deciding
nothing means each partner integration reinvents these under deadline, and the
first one that embeds the UI cross-origin makes the isolation properties
unprovable.

## Decision

The embed surface is a **signed, single-use, short-lived launch-ticket
handshake**, and the "button" is a thin launcher that never holds an Önvizit
secret. A partner embed tenant is a registered row in a second list,
`infra/tenants/embed_registry.yaml`, addressed only by `tenant_id` — the
connector-destination shape of ADR-026 — carrying constrained branding (data:
six-digit hex colours, a bounded display name, id-shaped asset/consent
references; never partner markup) and the recorded human facts a live tenant
costs; the file ships with dev-tier synthetic tenants only and a `prod` row is
refused without its executed DPA and brand-use permission (fail closed, zero
prod rows). The partner **backend** mints a ticket server-to-server
(`POST /embed/v1/launch-tickets`, authenticated) — HS256 over stdlib `hmac`
(the `room_tokens` primitive), carrying a closed claim set `{tenant_id, nonce,
iat, exp≤120s, purpose="previsit_intake"}` and **no clinical or personal value**
— signed with that tenant's own key resolved from OpenBao (inv. 14). The
patient's device presents the ticket (`POST /embed/v1/launch`); Önvizit verifies
the signature under the tenant's key, refuses an expired, replayed (single-use
nonce), tampered or wrong-purpose ticket, and returns only the tenant's theme
and the id of the consent document set to show — Önvizit then collects consent
through its own docs/legal-bound flow (inv. 4, inv. 18), `device_functions`
stays off (ADR-020), and the note flows back through the existing connector push
(ADR-026), so the embed adds no new outbound PHI path. Isolation holds because
the tenant is bound **inside** the signature and the signing key is the
tenant's: a ticket minted for one tenant cannot launch another, and there is no
free-text tenant request field to forge (inv. 37).

## Consequences

The first PR (INT-320) lands the mechanism, fail-closed, not a product: the
DB-free core is `packages/intake_platform/embed` (registry, ticket mint/verify,
launch-context resolution), the FastAPI surface is `services/api` under a new
`partner_embed` consent-scan marker caged to `/embed`, and the partner button is
`packages/embed-sdk` (TS strict) which calls the partner's own backend and only
ever opens an `https` Önvizit URL. No new database table, migration or
personal-data field is introduced: a partner-supplied patient identifier — the
correlation that would let the note flow back to a specific partner record — is
deliberately **out of scope** here, because linking it is a new personal-data
category and a new recipient relationship that needs human sign-off
(docs/backlog/blockers.md INT-320), and inventing a basis for it is forbidden
(inv. 17, inv. 18). The dev tenant's signing key lives in OpenBao and its
consent texts under its dev legal root are unauthored, so both the mint and the
consent step fail closed until seeded/authored — the honest state, not a stub.
What becomes easier: a partner integrates with a button and one server-to-server
call, and every isolation property is provable because nothing clinical crosses
an origin. What becomes harder, on purpose: a real partner costs recorded human
facts (DPA, brand permission, a seeded OpenBao key, authored consent texts, and
a production shared nonce store for multi-replica single-use) before it can go
live. Enforced by `tests/embed/*` and the consent route-scan
(`tests/legal/test_consent_guard.py`); recorded against files/10 §9 row `embed`
(docs/security/threat-model.md `embed`); this is the 00_STATE row for the
white-label direction. It re-litigates none of D1–D15 or ADR-001…027 and builds
within ADR-020 (device boundary), ADR-025 (egress) and ADR-026 (connector
destinations).
