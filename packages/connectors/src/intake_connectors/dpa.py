"""Processor-role DPA references (INT-162).

A connector destination and an inbound source are each bound to an executed
data-processing agreement (``dpa_ref``). In a hospital deployment INTAKE is the
**processor** (veri işleyen) and the hospital the controller — the same role the
SBYS regulation assigns hospital-software vendors (files/06 §1). The executed
DPA itself is a legal artefact the owner and counsel supply; it is HB-A15's to
name, and nothing here fabricates one.

What this module *is* is the closed list of clauses files/06 §7 requires such a
DPA to contain, each anchored to where this repository already meets the
processor duty behind it — the security annex is files/10, the sub-processor
list is the egress allow-list, and so on. It is a checklist a reviewer runs an
executed DPA against, and the input the KTS pack cites for its processor-duties
requirement. The 24-hour breach-notice window is a legal requirement quoted from
the source, not a measurement, so invariant 20 does not touch it.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["ProcessorDpaClause", "processor_role_references"]


@dataclass(frozen=True)
class ProcessorDpaClause:
    """One mandatory processor clause and where the repo meets its duty."""

    id: str
    requirement: str
    repo_anchor: str


#: files/06 §7's mandatory processor clauses. The order is the source's; the
#: ids are ours (stable handles for the KTS pack and a reviewer's checklist).
_CLAUSES: tuple[ProcessorDpaClause, ...] = (
    ProcessorDpaClause(
        id="role_allocation",
        requirement=(
            "KVKK m.8/12 controller↔processor role allocation: the hospital is controller, "
            "INTAKE is processor (files/06 §1, §7)"
        ),
        repo_anchor="files/06_COMPLIANCE_TR.md",
    ),
    ProcessorDpaClause(
        id="security_annex",
        requirement=(
            "security annex = files/10: the technical and organisational measures the "
            "processor applies (KVKK m.12)"
        ),
        repo_anchor="files/10_SECURITY_AND_TECHNICAL_MONITORING.md",
    ),
    ProcessorDpaClause(
        id="subprocessor_list",
        requirement=(
            "sub-processor list = the vendor register: only contracted vendors on the "
            "egress allow-list are reachable from the PHI path, which doubles as the KVKK "
            "transfer evidence (files/10 §7)"
        ),
        repo_anchor="files/10_SECURITY_AND_TECHNICAL_MONITORING.md",
    ),
    ProcessorDpaClause(
        id="audit_rights",
        requirement="the controller's audit rights over the processor (files/06 §7)",
        repo_anchor="files/06_COMPLIANCE_TR.md",
    ),
    ProcessorDpaClause(
        id="breach_notice",
        requirement=(
            "personal-data breach notice to the controller within 24 hours (files/06 §7); "
            "the breach packet templates are the controller/USOM/data-subject set"
        ),
        repo_anchor="files/06_COMPLIANCE_TR.md",
    ),
    ProcessorDpaClause(
        id="deletion_return",
        requirement=(
            "deletion or return of personal data on contract end, on the files/06 §3 "
            "retention matrix enforced by INT-036"
        ),
        repo_anchor="files/06_COMPLIANCE_TR.md",
    ),
    ProcessorDpaClause(
        id="execution_kep_eimza",
        requirement="execution by KEP / e-imza (qualified electronic signature) (files/06 §7)",
        repo_anchor="files/06_COMPLIANCE_TR.md",
    ),
)


def processor_role_references() -> tuple[ProcessorDpaClause, ...]:
    """The closed set of processor clauses an executed DPA must carry.

    The set is what a reviewer checks an executed DPA against and what the KTS
    pack cites for processor duties; the DPA content itself is HB-A15's to
    supply.
    """
    return _CLAUSES
