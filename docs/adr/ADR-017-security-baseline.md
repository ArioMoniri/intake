# ADR-017 · Security architecture baseline

Status: Accepted

## Context

One baseline inherited by every service and screen beats per-feature security decisions made under deadline. The threat model spans staff, patients, vendors-as-absence, and the ML pipeline itself.

## Decision

Keycloak OIDC + MFA for staff; OTP + device attestation + DPoP-bound rotating refresh tokens + biometrics for patients; OpenBao for secrets with dynamic DB creds and Transit envelope encryption per tenant; TCKN/phone tokenized; TLS 1.3 + mesh mTLS + default-deny NetworkPolicies; Coraza WAF + CrowdSec at ingress; deny-all egress on the PHI path; speech/documents/records are data never instructions; weights pinned by model_id@revision + sha256; cosign-signed images and protocol packs with SLSA provenance admitted by Kyverno; hash-chained WORM audit; Wazuh/Falco/CrowdSec feeds.

## Consequences

Invariants 13–16 and 19–22; the CI security gate set (INT-019) is never skipped or weakened inside the loop; every feature PR links its 10 §9 row.
