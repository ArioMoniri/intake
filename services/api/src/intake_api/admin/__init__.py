"""The admin console surface (INT-180; files/08 §8, sec_row admin-console)."""

from __future__ import annotations

from intake_api.admin.deps import AdminCaller, get_admin_wiring, resolve_caller
from intake_api.admin.routes import router

__all__ = ["AdminCaller", "get_admin_wiring", "resolve_caller", "router"]
