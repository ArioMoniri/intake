# ADR-002 · FHIR R4 canonical for exchange; openEHR deferred to a P3 export

Status: Accepted (amended 27 Aug 2026 — v1.4 said "openEHR canonical"; 00 §3 D8)

## Context

Every real consumer in P0–P2 — Doctor Link, the clinician note, connectors, e-Nabız deposit — is FHIR / ICD-10 / LOINC / ATC / text. No P0/P1 feature issues an AQL query; OPT authoring has no Python tooling; SNOMED CT is unavailable in Türkiye, removing much of openEHR's semantic advantage.

## Decision

FHIR R4 is the canonical exchange format. openEHR/EHRbase moves to P3 as an export, and every protocol slot keeps an openEHR archetype-path annotation so the P3 export is a migration, not a rewrite.

## Consequences

14–20 engineer-weeks recovered from P0/P1 (05 §2.1); the D8 corrections re-pointed INT-001/022/032/037. The archetype-path annotation is compiler-enforced from INT-041 so the P3 door stays open.
