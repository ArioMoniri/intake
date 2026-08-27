# ADR-022 · No accuracy claims

Status: Accepted

## Context

For MDSW the intended purpose is the qualification instrument, and an accuracy claim converts a described function into a claimed performance the technical file must substantiate — with Turkish evidence that does not exist. App Review 1.4.1 independently rejects unvalidatable health-accuracy claims. This is a claims-control rule, not modesty (00 §3 D16).

## Decision

No sensitivity, specificity, AUROC, WER, note-quality or extraction-accuracy figure appears anywhere it could be read as a performance representation: not docs/regulatory/, not docs/legal/, not patient or clinician copy, not marketing, not a store listing. Measurements are recorded in docs/evidence/ as dated internal measurements naming their corpus.

## Consequences

The claims-scan CI gate (INT-019) scans the regulatory and legal trees on every PR; a planted accuracy claim must fail it (07 §5). Internal measurement is unaffected — measure everything, publish nothing as a claim.
