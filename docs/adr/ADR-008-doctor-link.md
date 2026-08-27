# ADR-008 · Doctor Link as universal connector

Status: Accepted

## Context

No Turkish national FHIR read path exists (triple-sourced, 00 §2), HBYS integrations are bilateral and slow, and the clinician on the other side may have nothing but a phone. The one universal integration point is a clinician with a browser.

## Decision

The default delivery channel is Doctor Link: a 128-bit tokenised web view + OTP + expiry + view limits + revocation + watermark + audited access, with PDF and QR. Structured connectors (FHIR push, HBYS kit) are additive, per-tenant, and never a launch dependency.

## Consequences

The product works at any hospital from day one; every open is audited and patient-visible (KVKK m.11). Connector work (INT-160+) becomes an optimisation, not a gate.
