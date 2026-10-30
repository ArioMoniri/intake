"""INT-580 — the OTP SMS's words, and the line that binds its code to the app.

The owner's order of 28 Oct 2026 asked, against SMS hijacking and phishing, for
a message that carries the code and the app name and nothing else, and for the
domain-bound one-time-code line, so that iOS offers the code only to the app.

**The words** live in one tr resource, ``sms_copy.tr.json`` (tr is the source
of truth, invariant 5): ``Önvizit doğrulama kodunuz: {code}. Bu kodu kimseyle
paylaşmayınız.`` — the siz register, ``-iniz`` for the instruction, and a test
runs it through PolicyGuard. Both SMS adapters render from it; Netgsm's OTP
product refuses Turkish letters, so it gets the same words folded to ASCII
(:func:`fold_ascii`). No link and no PHI can enter: the only slot is the code.

**The domain-bound line** is WebKit's format, ``@<domain> #<code>`` as the
message's last line. iOS then offers the code only inside an app whose
``webcredentials:`` associated domain is ``<domain>``, never on a look-alike
website a phisher sends the patient to. The domain is never invented: it is
read from the app's own entitlement, ``ios.associatedDomains`` in
``apps/mobile/app.json``. The line is sent only for exactly ONE
``webcredentials:`` entry that is a public DNS name (two or more labels, letters,
digits and hyphens, no developer-mode suffix) and that keeps the longest
message inside one SMS segment. Anything else — no entry, two entries, a
malformed or developer-mode one, an unreadable config — sends no line. A wrong
line would steer the autofill somewhere else; no line only gives it up.

The shipped app declares no associated domain yet (the final host name is the
owner's, HB-I14, and the domain must also serve an ``apple-app-site-association``
file naming the app), so today no line is sent. That state is pinned by a test,
and the day the app gains the entitlement the line starts going out with no
other change.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Final

__all__ = [
    "MAX_CODE_DIGITS",
    "MOBILE_APP_CONFIG_PATH",
    "OTP_BODY_TR",
    "SEGMENT_LIMIT",
    "SMS_COPY_PATH",
    "associated_domain",
    "fold_ascii",
    "render_otp_sms",
]

logger = logging.getLogger("intake_api.sms_copy")

SMS_COPY_PATH: Final = Path(__file__).with_name("sms_copy.tr.json")
#: The app config the domain is read from, relative to the repo root (the
#: msisdn_allocation idiom); ApiSettings carries it so a test can point it.
MOBILE_APP_CONFIG_PATH: Final = Path("apps/mobile/app.json")
#: One GSM-7 segment with an alphanumeric sender (Netgsm's code 20).
SEGMENT_LIMIT: Final = 155
#: The longest code an adapter accepts; the domain must fit beside it.
MAX_CODE_DIGITS: Final = 10

_WEBCREDENTIALS = "webcredentials:"
_LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
_PUBLIC_NAME = re.compile(rf"(?:{_LABEL}\.)+[a-z]{{2,63}}")
_ASCII_FOLD: Final = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")


def _load_body() -> str:
    document = json.loads(SMS_COPY_PATH.read_text(encoding="utf-8"))
    body = document["sms.otp.body"]
    if not isinstance(body, str) or body.count("{code}") != 1:
        raise ValueError("sms_copy.tr.json: sms.otp.body must carry the one {code} slot")
    return body


#: The OTP SMS body, in Turkish, with its one ``{code}`` slot.
OTP_BODY_TR: Final = _load_body()


def fold_ascii(text: str) -> str:
    """The Turkish letters folded to their ASCII bases (the OTP product's rule)."""
    return text.translate(_ASCII_FOLD)


def render_otp_sms(code: str, *, domain: str | None = None, ascii_only: bool = False) -> str:
    """The message for one code: the body, and the domain-bound line when the
    app's entitlement names a domain."""
    body = OTP_BODY_TR.format(code=code)
    if domain is not None:
        body = f"{body}\n\n@{domain} #{code}"
    return fold_ascii(body) if ascii_only else body


def associated_domain(app_config: Path) -> str | None:
    """The one ``webcredentials:`` domain the app is entitled to, or None.

    None whenever the answer is not unambiguous, and the reason is logged by
    name (never a value from the file): a missing or unreadable config, no
    entry, more than one, or one that is not a public name or would push the
    longest message past a segment."""
    try:
        config = json.loads(app_config.read_text(encoding="utf-8"))
        entries = config["expo"]["ios"].get("associatedDomains")
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        logger.info("domain-bound OTP line off: the mobile app config is not readable")
        return None
    if entries is None:
        logger.info(
            "domain-bound OTP line off: the app declares no associated domain (owner input)"
        )
        return None
    if not isinstance(entries, list) or not all(isinstance(e, str) for e in entries):
        logger.warning("domain-bound OTP line off: ios.associatedDomains is not a list of names")
        return None
    credentials: list[str] = [
        str(e)[len(_WEBCREDENTIALS) :] for e in entries if str(e).startswith(_WEBCREDENTIALS)
    ]
    if len(credentials) != 1:
        logger.info(
            "domain-bound OTP line off: the app declares %d webcredentials domains, not one",
            len(credentials),
        )
        return None
    [domain] = credentials
    if not _PUBLIC_NAME.fullmatch(domain) or len(domain) > 253:
        logger.warning("domain-bound OTP line off: the webcredentials domain is not a public name")
        return None
    longest = render_otp_sms("9" * MAX_CODE_DIGITS, domain=domain, ascii_only=True)
    if len(longest) > SEGMENT_LIMIT:
        logger.warning("domain-bound OTP line off: the domain would push the SMS past one segment")
        return None
    return domain
