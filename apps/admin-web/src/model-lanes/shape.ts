/**
 * INT-428 — the two structural refusals the Model lanes view-model applies to
 * every object of the `GET /admin/model-lanes` document before it reads a
 * single field:
 *
 * - {@link ModelLanesShapeRefused} — an object whose key set is not exactly
 *   the one `intake.admin.model_lanes.v1` defines. A field the page does not
 *   know is a field it would silently drop, and a field it expects and does
 *   not find would read as blank; both mean the two sides have drifted.
 * - {@link ModelLanesSecretLeaked} — anything that carries a credential: a
 *   field named like one (`api_key`, `secret`, `token` …) anywhere in the
 *   tree, or a string shaped like a provider key or a bearer header. The API
 *   discloses a provider key as set / not set and its last four characters,
 *   and nothing more; a document that says more is refused whole, and the
 *   refusal names the path, never the value.
 */
import { OpsPayloadRefused } from "../ops/guards";

export class ModelLanesShapeRefused extends OpsPayloadRefused {}
export class ModelLanesSecretLeaked extends OpsPayloadRefused {}

/** A field name that carries a credential. `key` alone is a model selection
 * key or the key-state block, and is not one. */
const SECRET_FIELD =
  /(^|_)(api_?key|secret|token|password|passphrase|bearer|authorization|credential|private_key)s?($|_)/i;

/** A provider API key or an authorization header, wherever it appears. */
const SECRET_VALUE = /(^|[^A-Za-z0-9])sk-[A-Za-z0-9_-]{16,}|^bearer\s/i;

/** Walk the whole document; refuse on the first credential-bearing name or value. */
export function noSecrets(value: unknown, path: string): void {
  if (typeof value === "string") {
    if (SECRET_VALUE.test(value)) {
      throw new ModelLanesSecretLeaked("secret_value", `${path} is shaped like a credential`);
    }
    return;
  }
  if (value === null || typeof value !== "object") return;
  if (Array.isArray(value)) {
    value.forEach((inner, index) => noSecrets(inner, `${path}[${index}]`));
    return;
  }
  for (const [key, inner] of Object.entries(value)) {
    if (SECRET_FIELD.test(key)) {
      throw new ModelLanesSecretLeaked("secret_field", `${path}.${key} names a credential`);
    }
    noSecrets(inner, `${path}.${key}`);
  }
}

/** The object at `what`, when its keys are exactly `required` (plus any of `optional`). */
export function closed(
  value: unknown,
  required: readonly string[],
  what: string,
  optional: readonly string[] = [],
): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new ModelLanesShapeRefused("not_an_object", `${what} is not an object`);
  }
  const record = value as Record<string, unknown>;
  for (const key of Object.keys(record)) {
    if (!required.includes(key) && !optional.includes(key)) {
      throw new ModelLanesShapeRefused("unexpected_field", `${what}.${key} is not in the schema`);
    }
  }
  for (const key of required) {
    if (!(key in record)) {
      throw new ModelLanesShapeRefused("missing_field", `${what}.${key} is missing`);
    }
  }
  return record;
}

export function list(value: unknown, what: string): unknown[] {
  if (!Array.isArray(value)) {
    throw new ModelLanesShapeRefused("not_a_list", `${what} is not a list`);
  }
  return value;
}

export function bool(value: unknown, what: string): boolean {
  if (typeof value !== "boolean") {
    throw new ModelLanesShapeRefused("not_a_boolean", `${what} is not a boolean`);
  }
  return value;
}

/** A finite, non-negative measurement or `null`. */
export function figure(value: unknown, what: string): number | null {
  if (value === null) return null;
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
    throw new ModelLanesShapeRefused("not_a_figure", `${what} is not a measurement`);
  }
  return value;
}
