"""services/api — the INTAKE JSON API, **dev-tier slice** (INT-197).

Owner directive: the demo tier needs a real backend — the two synthetic
accounts must actually create visits, write notes and upload documents
against the real INT-030 schema, not against in-app fixtures.

This package is EXPLICITLY the dev tier:

- auth is a dev bearer over exactly two synthetic accounts
  (:mod:`intake_api.dev_fixture`); the tokens come from the environment only
  and the service fails closed without them. Real OIDC auth is INT-131.
- every response carries ``X-Intake-Auth-Tier: dev`` so no client can
  mistake this tier for the real thing.

Everything else is production-shaped: RLS tenant context on every request,
consent-scope checks and hash-chained audit on every clinical read/share
(invariant 4), envelope encryption for note payloads (invariant 14), the
invariant-15 monitoring contract, and ids-only logging (invariant 6).
"""

__all__ = ["__version__"]

__version__ = "0.1.0"
