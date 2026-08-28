"""Machine-readable error bodies (INT-197). Every refusal is a flat
``{"error": <code>, ...}`` object — codes, never narrative, so no PHI can
travel in an error (invariant 6) and the mobile app can map codes to its own
tr copy (invariant 5)."""

from __future__ import annotations

from fastapi import HTTPException

__all__ = [
    "consent_required",
    "dev_auth_unconfigured",
    "forbidden",
    "not_found",
    "unauthorized",
    "visit_invalid",
]


def unauthorized() -> HTTPException:
    return HTTPException(status_code=401, detail={"error": "unauthorized"})


def forbidden() -> HTTPException:
    return HTTPException(status_code=403, detail={"error": "forbidden"})


def consent_required(scope: str) -> HTTPException:
    return HTTPException(status_code=403, detail={"error": "consent_required", "scope": scope})


def not_found() -> HTTPException:
    return HTTPException(status_code=404, detail={"error": "not_found"})


def visit_invalid(reason: str) -> HTTPException:
    return HTTPException(status_code=422, detail={"error": reason})


def dev_auth_unconfigured() -> HTTPException:
    return HTTPException(status_code=503, detail={"error": "dev_auth_unconfigured"})
