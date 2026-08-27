/**
 * Clinical schema identifiers. The Pydantic/TS clinical models, event schemas
 * (csat.v1, nps.v1, audit.v1, admin_audit.v1) and the FHIR mappers arrive with
 * INT-031; the metrics catalogue with INT-025. This module owns the one thing
 * every one of those shares: the versioned schema-id convention.
 */

export const SCHEMA_NAMESPACE = "intake.clinical" as const;

const NAME_PATTERN = /^[a-z][a-z0-9_.]*$/;

/** Build a fully-qualified, versioned schema id, e.g. `intake.clinical.csat.v1`. */
export function schemaId(name: string, version: number): string {
  if (!NAME_PATTERN.test(name)) {
    throw new Error(`invalid schema name: ${name}`);
  }
  if (!Number.isInteger(version) || version < 1) {
    throw new Error(`invalid schema version: ${version}`);
  }
  return `${SCHEMA_NAMESPACE}.${name}.v${version}`;
}
