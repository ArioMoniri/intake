"""The fixed-string keys the DSAR export document renders from (INT-037).

This module declares a KEY SET, not copy. The Turkish wording behind every
key is authored by counsel into ``docs/legal/strings.yaml`` under INT-210
(files/06 §7, "Fixed legal copy … PolicyGuard-protected"), and until it exists
:class:`intake_platform.legal.LegalStringsCatalog` refuses and the export
fails closed. Nothing here may ever carry a default: a "temporary" Turkish
string in source is exactly the drafted-legal-copy this project forbids, and
it would be indistinguishable from counsel's own once merged.

``dsar_export.footer`` is deliberately its OWN key rather than a reuse of the
files/06 §7 note footer: whether the KVKK m.13 response document carries the
1219 m.8 clinical disclaimer verbatim, a variant, or nothing at all is
counsel's call, and encoding a guess here would take that call from them.
"""

from __future__ import annotations

from typing import Final

__all__ = ["DSAR_EXPORT_SECTION_KEYS", "DSAR_EXPORT_STRING_KEYS", "section_key"]

#: Export-document sections, in the order the document renders them. The ids
#: are ours (technical); the headings are counsel's (Turkish).
#:
#: INT-395 added the last four, for the tables the inventory annotations put
#: under the subject's access right and no existing heading fits: the learned
#: facts files/09 §3 calls "exported/deletable", the satisfaction comment, the
#: notification opt-out register (a refusal under row 6563-İYS, deliberately
#: not a consent — ``consent_guard.NotificationPreferenceDeclaration``) and
#: the guardian link (its own inventory category, never filed as consent).
#: Each is one more heading for counsel to author; until then the export
#: refuses exactly as it does for the first nine.
#:
#: INT-582 added ``passkeys``: the public half of each patient passkey (D36),
#: its own inventory category (authentication_credential), filed under no
#: other heading. One more heading for counsel; the export refuses until then.
DSAR_EXPORT_SECTIONS: Final[tuple[str, ...]] = (
    "visits",
    "notes",
    "documents",
    "consents",
    "shares",
    "rectifications",
    "requests",
    "learned_facts",
    "feedback",
    "preferences",
    "guardians",
    "passkeys",
)


def section_key(section: str) -> str:
    return f"dsar_export.section.{section}"


DSAR_EXPORT_SECTION_KEYS: Final[tuple[str, ...]] = tuple(
    section_key(section) for section in DSAR_EXPORT_SECTIONS
)

#: Every fixed string the export document cannot be produced without.
DSAR_EXPORT_STRING_KEYS: Final[tuple[str, ...]] = (
    "dsar_export.title",
    "dsar_export.footer",
    *DSAR_EXPORT_SECTION_KEYS,
)
