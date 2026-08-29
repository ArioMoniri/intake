/**
 * Clinical schemas, TS side (INT-031). This module owns the versioned
 * schema-id convention; the generated types in ./generated/models are emitted
 * from the pydantic models via the OpenAPI bundle (clinical_schemas.codegen)
 * and re-exported here — regenerate with `make schemas-codegen`, never edit
 * by hand. The FHIR mappers arrive with INT-033; the metrics catalogue with
 * INT-025.
 */

export type * from "./generated/models";

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
