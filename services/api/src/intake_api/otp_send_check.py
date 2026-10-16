"""INT-528 — send ONE real OTP SMS to the synthetic host's allow-listed number.

Owner authorisation, 16 Oct 2026: one real code to the single number on the
synthetic host's SMS test allow-list, once INT-528, the egress patch and the
deploy are live, and only when the owner runs it. ``infra/staging/netgsm_test_otp.sh``
runs this inside the api container:

    docker compose -p intake-staging exec -T api python -m intake_api.otp_send_check

It builds the delivery adapter exactly as the API does
(:func:`intake_api.otp_netgsm.otp_delivery_from_settings` over
``ApiSettings.from_env()``), so the egress row, the runtime gate, the SMS-only
proxy, the OpenBao document and the test allow-list must all be live. It sends
to the list's one number, which it never prints and never takes as an
argument, one random code that nothing stores or verifies, and it prints only
the vendor's job id (code 00) or the refusal by its typed names (invariant 6).
Nothing in the API calls it.
"""

from __future__ import annotations

import asyncio
import secrets
import sys
from collections.abc import Callable
from typing import TextIO

from intake_api.auth_store import OTP_CODE_DIGITS
from intake_api.otp import OtpDeliveryAdapter, OtpDeliveryError
from intake_api.otp_netgsm import NetgsmSmsDeliveryAdapter, otp_delivery_from_settings
from intake_api.settings import ApiSettings
from intake_api.sms_recipients import SmsTestAllowlist

__all__ = ["main"]

#: Exit codes: sent, refused by the vendor or unconfigured, refused before sending.
SENT, NOT_SENT, REFUSED = 0, 1, 2


def main(
    out: TextIO = sys.stdout,
    settings_factory: Callable[[], ApiSettings] = ApiSettings.from_env,
    delivery_factory: Callable[[ApiSettings], OtpDeliveryAdapter | None] = (
        otp_delivery_from_settings
    ),
) -> int:
    settings = settings_factory()
    if settings.dev_tier_expected:
        print("refused before sending: this check runs on the synthetic host only", file=out)
        return REFUSED
    delivery = delivery_factory(settings)
    if delivery is None:
        print(
            "not sent: the OTP tier is unconfigured and would answer 503 "
            "(the API log names the missing piece: egress row, runtime gate or OpenBao)",
            file=out,
        )
        return NOT_SENT
    gate = delivery.recipients if isinstance(delivery, NetgsmSmsDeliveryAdapter) else None
    if not isinstance(gate, SmsTestAllowlist) or gate.count != 1:
        count = gate.count if isinstance(gate, SmsTestAllowlist) else "no"
        print(
            f"refused before sending: this check sends to the single number on the "
            f"synthetic host's SMS test allow-list, and the list holds {count}",
            file=out,
        )
        return REFUSED
    [phone] = gate.numbers
    code = f"{secrets.randbelow(10**OTP_CODE_DIGITS):0{OTP_CODE_DIGITS}d}"
    try:
        receipt = asyncio.run(delivery.send(phone_e164=phone, code=code))
    except OtpDeliveryError as exc:
        refusal = getattr(exc, "refusal", None)
        print(
            f"not sent: reason={exc.reason} refusal={refusal or '-'} "
            f"http_status={exc.status_code or '-'} vendor_code={exc.vendor_code or '-'}",
            file=out,
        )
        return NOT_SENT
    print(f"accepted: code 00, job id {receipt.delivery_id}", file=out)
    return SENT


if __name__ == "__main__":
    sys.exit(main())
