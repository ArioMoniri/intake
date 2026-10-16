"""Fill the Önvizit App Store listing in App Store Connect as an editable draft (INT-495).

Dry run by default: prints the plan — resource, field names and every blocked
field — and sends nothing. ``--apply`` writes the plan's draft edits and nothing
else; it needs the owner's own eas.json (``--eas-json``), whose
``submit.production.ios`` names the key file, key id, issuer id and app id. Those
are read at run time and never printed. ``--placement-groups`` reads the App
Asset Library reference data and prints the placement group identifiers, for
docs/store/asc/assets.yaml.

This script never submits for review, never releases, and never touches
pricing, availability, agreements or the App Review sign-in.

Exit codes: 0 done; 1 App Store Connect refused or holds nothing editable;
2 a usage error or served copy App Store Connect would refuse; 3 nothing is
served yet (HB-L21), the fail-closed state.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import asc_client
import asc_plan
from intake_platform.legal.documents import LegalDocumentError
from intake_platform.store.eas_metadata import StoreConfigError
from intake_platform.store.listing import StoreListingError, StoreListingMissingError

REPO = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", type=Path, default=REPO)
    parser.add_argument("--apply", action="store_true", help="write the draft (owner only)")
    parser.add_argument("--placement-groups", action="store_true", help="read-only lookup")
    parser.add_argument("--eas-json", type=Path, help="the owner's eas.json, read at run time")
    args = parser.parse_args(argv)
    if (args.apply or args.placement_groups) and args.eas_json is None:
        parser.error("--apply and --placement-groups need --eas-json <the owner's eas.json>")

    if args.placement_groups:
        creds = asc_client.Credentials.from_eas_json(args.eas_json)
        status, data = asc_client.HttpTransport(creds).request("GET", "/v1/appAssetLibraryRefData")
        print(f"GET appAssetLibraryRefData -> {status}")
        groups = sorted(set(re.findall(r'"([A-Z][A-Z0-9_]*_PROFILE)"', json.dumps(data))))
        print("\n".join(f"GROUP {group}" for group in groups))
        return 0 if status < 300 else 1

    try:
        plan = asc_plan.build_plan(args.repo)
    except StoreListingMissingError as exc:
        print(f"asc_listing: BLOCKED — {exc}")
        return 3
    except (StoreConfigError, StoreListingError, LegalDocumentError, asc_plan.PlanError) as exc:
        print(f"asc_listing: REFUSED — {exc}")
        return 2
    if not args.apply:
        sys.stdout.write(asc_plan.render_plan(plan))
        return 0

    creds = asc_client.Credentials.from_eas_json(args.eas_json)
    try:
        asc_client.apply_plan(plan, asc_client.HttpTransport(creds), app_id=creds.app_id, log=print)
    except asc_client.ApplyError as exc:
        print(f"asc_listing: STOPPED — {exc}")
        return 1
    for reason in plan.blocked:
        print(f"BLOCKED {reason}")
    print("asc_listing: draft written. Nothing was submitted for review or released.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
