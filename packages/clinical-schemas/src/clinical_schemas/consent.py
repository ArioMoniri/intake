"""Consent scope schema (INT-031).

files/06 §2.1 is the closed purpose list ("Purposes exactly: …") and the
record each consent stores ({version, text_hash, ts, channel, evidence}).
The persistence twin is ``intake_platform.db.models.Consent`` (INT-030:
scope/version/granted_at/revoked_at); the audit twin is the id-shaped
``consent_scope_ref`` every chain entry carries (INT-016, invariant 4).
``lane:acoustic`` is deliberately absent — it is an investigational-device
ICF, not a consent purpose (files/06 §2.4).
"""

from __future__ import annotations

import enum

from pydantic import AwareDatetime, Field, model_validator

from clinical_schemas.common import FrozenModel, Ref, Sha256


class ConsentPurpose(enum.StrEnum):
    """The closed purpose list of files/06 §2.1 — no more, no fewer."""

    CORE = "core"
    VOICE = "voice"
    WELLBEING = "wellbeing"
    LANE_AFFECT = "lane:affect"
    LANE_LINGUISTIC = "lane:linguistic"
    DOCUMENTS = "documents"
    LEARNING_PERSONAL = "learning:personal"
    LEARNING_SERVICE_IMPROVEMENT = "learning:service_improvement"
    SATISFACTION = "satisfaction"
    SHARE = "share"
    RESEARCH = "research"


class ConsentChannel(enum.StrEnum):
    """Collection channel (files/06 §1 KVKK-10 row: layered aydınlatma per
    channel — app, kiosk, clinician, admin, web)."""

    APP = "app"
    KIOSK = "kiosk"
    CLINICIAN = "clinician"
    ADMIN = "admin"
    WEB = "web"


class ShareScope(FrozenModel):
    """Parameters of a share grant (files/06 §2.1:
    ``share:{recipient,visit,sections,expiry}``)."""

    recipient: Ref = Field(
        description="Who receives the share, as an id (files/06 §2.1 share.recipient)."
    )
    visit: Ref = Field(description="The visit being shared (files/06 §2.1 share.visit).")
    sections: tuple[str, ...] = Field(
        min_length=1,
        description="Note section ids exposed by the share (files/06 §2.1 share.sections; "
        "INT-030 shares.scope_sections carries section ids only).",
    )
    expiry: AwareDatetime = Field(
        description="Hard expiry of the share (files/06 §2.1 share.expiry; "
        "INT-030 shares.expires_at, ≤ 72 h default per files/06 §3)."
    )


class ConsentScope(FrozenModel):
    """One granted consent scope — the thing every clinical read/share checks
    (invariant 4) and every audit entry references by id (INT-016)."""

    purpose: ConsentPurpose = Field(
        description="Consent purpose id from the closed files/06 §2.1 list."
    )
    version: str = Field(
        min_length=1,
        description="Version of the consent text presented (files/06 §2.1; INT-030 "
        "consents.version, hash-bound to docs/legal — invariant 18).",
    )
    text_hash: Sha256 = Field(
        description="SHA-256 of the exact consent text shown (files/06 §2.1 text_hash; "
        "texts render only from docs/legal/ with hash binding — invariant 18)."
    )
    granted_at: AwareDatetime = Field(
        description="Grant instant (files/06 §2.1 ts; INT-030 consents.granted_at)."
    )
    channel: ConsentChannel = Field(
        description="Which surface collected the grant (files/06 §2.1 channel; §1 KVKK-10)."
    )
    evidence: Ref = Field(
        description="Id of the acceptance evidence record (files/06 §2.1 evidence) — "
        "an id, never the evidence itself (invariant 6)."
    )
    share: ShareScope | None = Field(
        default=None,
        description="Share parameters — required exactly when purpose is ``share`` "
        "(files/06 §2.1 share:{recipient,visit,sections,expiry}).",
    )
    revoked_at: AwareDatetime | None = Field(
        default=None,
        description="Withdrawal instant; None while the grant stands (INT-030 "
        "consents.revoked_at; files/06 §2.1 withdrawal as easy as grant).",
    )

    @model_validator(mode="after")
    def _share_scope_iff_share_purpose(self) -> ConsentScope:
        if (self.purpose is ConsentPurpose.SHARE) != (self.share is not None):
            raise ValueError(
                "share parameters are required exactly when purpose is 'share' (files/06 §2.1)"
            )
        return self
