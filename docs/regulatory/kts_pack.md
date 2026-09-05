# KTS (SBYS Kayıt Tescil) application pack

> GENERATED from `packages/connectors/src/intake_connectors/kts_requirements.yaml`
> by `intake_connectors.kts.build_kts_pack` (INT-162). Do not edit by hand — a
> test asserts this file equals the generator's output. Legal source: files/06
> §63 (SBYS-6). The pack is NOT complete: the human-legal items are blocked and
> fail closed, exactly as `docs/legal/documents.yaml` does.

Pack version: 1  ·  complete: false

## Requirements

| id | requirement | status | anchor |
| --- | --- | --- | --- |
| usvs_conformance | MoH data-definitions (USVS) conformance — the mapping mechanism | present | packages/connectors/src/intake_connectors/usvs_map.yaml |
| data_submission_services | Data-submission services followed (SBYS data-gönderim) | present | files/06_COMPLIANCE_TR.md |
| version_notes | Version notes / iteration record | present | docs/PROGRESS.md |
| processor_duties | Processor duties (veri işleyen) under the hospital DPA | present | files/06_COMPLIANCE_TR.md |
| security_annex | Security annex = files/10 (KVKK m.12 technical measures) | present | files/10_SECURITY_AND_TECHNICAL_MONITORING.md |
| iso27001_pursuit | ISO/IEC 27001 pursuit (tender requirement; the m.6/3 paragraph was repealed 03.07.2026) | present | files/06_COMPLIANCE_TR.md |
| sbsgm_published_document_list | The SBSGM-published KTS required-document list | blocked | — |
| usvs_dictionary_source | The committed USVS data-dictionary the code bindings are checked against | blocked | — |

## Blocked — awaiting a named human

- **sbsgm_published_document_list** — The required documents are the live list SBSGM publishes, which files/06 §63 says to track and no committed source in this repository holds. Until the current list is recorded, the pack cannot enumerate every artefact a registration needs, so it is not complete.
- **usvs_dictionary_source** — The USVS code bindings in usvs_map.yaml are draft_needs_source: no committed USVS dictionary vouches for a code or an element, so conformance is a mechanism awaiting content, not a proven fact.

See `docs/backlog/blockers.md` (INT-162) and `files/HUMAN_BLOCKERS.md` for the
one sentence each blocked item needs answered.

## Processor-role DPA clauses (files/06 §7)

The executed DPA is HB-A15's to supply; these are the clauses it must carry.

| clause | requirement | anchor |
| --- | --- | --- |
| role_allocation | KVKK m.8/12 controller↔processor role allocation: the hospital is controller, INTAKE is processor (files/06 §1, §7) | files/06_COMPLIANCE_TR.md |
| security_annex | security annex = files/10: the technical and organisational measures the processor applies (KVKK m.12) | files/10_SECURITY_AND_TECHNICAL_MONITORING.md |
| subprocessor_list | sub-processor list = the vendor register: only contracted vendors on the egress allow-list are reachable from the PHI path, which doubles as the KVKK transfer evidence (files/10 §7) | files/10_SECURITY_AND_TECHNICAL_MONITORING.md |
| audit_rights | the controller's audit rights over the processor (files/06 §7) | files/06_COMPLIANCE_TR.md |
| breach_notice | personal-data breach notice to the controller within 24 hours (files/06 §7); the breach packet templates are the controller/USOM/data-subject set | files/06_COMPLIANCE_TR.md |
| deletion_return | deletion or return of personal data on contract end, on the files/06 §3 retention matrix enforced by INT-036 | files/06_COMPLIANCE_TR.md |
| execution_kep_eimza | execution by KEP / e-imza (qualified electronic signature) (files/06 §7) | files/06_COMPLIANCE_TR.md |
