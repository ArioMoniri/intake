"""Record the `GET /admin/models` body the admin-web spec runs against.

`apps/admin-web/e2e/models.spec.ts` needs a payload to render. There are two
ways to give it one and only one of them is honest: write a mock by hand, or
record what the server actually serves. A hand-written mock is the second,
hand-kept copy of the self-hosting registry that invariant 13 exists to
forbid — it would keep passing on the day the registry changed and the console
stopped matching it.

So this script emits the same projection the route emits, and
``tests/admin/test_models_module.py::TestFixtureIsRecordedFromTheApi`` holds
the committed file against the live response on every ``make check``. If the
registry changes and nobody re-runs this, the Python lane goes red — the
fixture cannot silently rot.

Run it from the repository root::

    make admin-fixtures
"""

from __future__ import annotations

import json
from pathlib import Path

from intake_api.admin.models_source import load_models_module, load_probe_sweep
from intake_api.admin.views import models_module_view

FIXTURE = Path("apps") / "admin-web" / "e2e" / "fixtures" / "models.payload.json"


def main() -> int:
    sweep = load_probe_sweep()
    payload = models_module_view(load_models_module(sweep), sweep)
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    rows = len(payload["rows"])
    blocked = payload["release"]["blocked"]
    print(f"recorded {FIXTURE} — {rows} rows, release blocked: {blocked}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
