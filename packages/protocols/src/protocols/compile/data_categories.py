"""The data-category serve gates (INT-349; owner decision D3 of 2026-09-26).

Four refusals, each re-checked on the resolved slot the way the rest of the
compiler re-checks what the DSL schema already refused:

- **Unknown category.** The set is closed. A value that got past the schema
  (``model_construct``) is refused here as well.
- **Incomplete register row.** A slot whose category row in
  docs/legal/data-categories.yaml is missing any counsel field is never
  compiled into a served pack. No register at all means no rows, so every
  category except ``general_health`` refuses (fail closed).
- **Wrong deployment (INT-474).** ``household``, ``relatives_health`` and
  ``partner_fertility`` are about a person who is not the patient, and their
  ground for that person is the hospital's. They compile only for the
  hospital-controller deployment, whatever the register row says, and never
  when no deployment role was given (:mod:`protocols.deployment_role`).
- **Relaxed category.** A later pack in the chain may tag a slot its parent
  left ``general_health``. It may not drop or change a category the parent
  set, because redeclaring the slot would write its answers without the
  encryption and the register row that category requires.

There is no bypass and no dev flag. When counsel fills a row, the row opens
the register gate and nothing else does (HUMAN_BLOCKERS Rule 2); for the
three other-subject categories the deployment gate stays where it is.
"""

from __future__ import annotations

from collections.abc import Sequence

from protocols.bindings import fhir_link_id
from protocols.compile.errors import Refusal, RefusalCode
from protocols.data_register import DATA_REGISTER_PATH, DataCategoryRegister
from protocols.deployment_role import DeploymentRole, admits, refusal_reason
from protocols.dsl import Slot
from protocols.pack import ProtocolPack
from protocols.types import DataCategory

__all__ = ["category_relaxation_refusals", "slot_category_refusals"]


def slot_category_refusals(
    link_id: str,
    slot: Slot,
    register: DataCategoryRegister,
    *,
    deployment_role: DeploymentRole | None,
) -> list[Refusal]:
    """Refuse a resolved slot whose category is unknown, whose row is
    incomplete, or whose category this deployment may not serve. The last two
    are independent and both are reported."""
    # typed as the enum, but a slot built with model_construct carries whatever
    # it was given, so the value is re-parsed rather than trusted
    raw = slot.data_category
    try:
        category = DataCategory(raw)
    except ValueError:
        return [
            Refusal(
                code=RefusalCode.DATA_CATEGORY_UNKNOWN,
                subject=link_id,
                message=f"INT-349: {raw!r} is not a data category. The set is closed "
                "(general_health plus the owner's D3 categories), and adding one is "
                "adding a category of personal data, which is a human decision",
            )
        ]
    refusals: list[Refusal] = []
    missing = register.missing(category)
    if missing:
        refusals.append(
            Refusal(
                code=RefusalCode.DATA_CATEGORY_REGISTER_INCOMPLETE,
                subject=link_id,
                message=f"INT-349: data category {category.value!r} is not servable while "
                f"its row in {DATA_REGISTER_PATH.as_posix()} is incomplete (missing: "
                f"{', '.join(missing)}). Counsel supplies these: the KVKK m.6 basis, "
                "retention, recipients and consent scope (owner decision D3). The gate "
                "stays closed until they do (CLAUDE.md invariant 18)",
            )
        )
    if not admits(category, deployment_role):
        refusals.append(
            Refusal(
                code=RefusalCode.DATA_CATEGORY_DEPLOYMENT_ROLE,
                subject=link_id,
                message=refusal_reason(category, deployment_role),
            )
        )
    return refusals


def category_relaxation_refusals(packs: Sequence[ProtocolPack]) -> list[Refusal]:
    """Refuse a later pack that drops or changes a category an earlier one set.

    ``packs`` is in application order, root first, as the resolver folds them.
    """
    declared: dict[tuple[str, str], tuple[str, DataCategory]] = {}
    refusals: list[Refusal] = []
    for pack in packs:
        for section_id, section in pack.sections.items():
            for key, slot in section.slots.items():
                where = (section_id, key)
                earlier = declared.get(where)
                if (
                    earlier is not None
                    and earlier[1] is not DataCategory.GENERAL_HEALTH
                    and slot.data_category != earlier[1]
                ):
                    refusals.append(
                        Refusal(
                            code=RefusalCode.DATA_CATEGORY_RELAXED,
                            subject=f"{pack.id}:{fhir_link_id(section_id, key)}",
                            message=f"INT-349: {earlier[0]} tags this slot "
                            f"{earlier[1].value!r}. A later pack may keep that category, "
                            "never drop or change it: redeclaring the slot as "
                            f"{str(slot.data_category)!r} would store its answers without "
                            "the encryption and the register row its category requires",
                        )
                    )
                    continue
                declared[where] = (pack.id, slot.data_category)
    return refusals
