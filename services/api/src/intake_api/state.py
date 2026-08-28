"""Per-app dependency container (INT-197): the wired engine, audit writer
and envelope cipher, reachable from any route via ``Depends(get_state)`` —
tests inject their own, the env path builds the real ones (app.py)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, cast

from fastapi import Depends, Request
from intake_platform.envelope import EnvelopeCipher
from sqlalchemy.ext.asyncio import AsyncEngine

from intake_api.audit import AuditWriter
from intake_api.settings import ApiSettings

__all__ = ["ApiState", "State", "get_state"]


@dataclass
class ApiState:
    settings: ApiSettings
    engine: AsyncEngine
    audit: AuditWriter
    cipher: EnvelopeCipher


def get_state(request: Request) -> ApiState:
    return cast(ApiState, request.app.state.api)


State = Annotated[ApiState, Depends(get_state)]
