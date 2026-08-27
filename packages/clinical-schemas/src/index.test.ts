import { describe, expect, it } from "vitest";

import { SCHEMA_NAMESPACE, schemaId } from "./index";

describe("schemaId", () => {
  it("builds versioned event ids", () => {
    expect(schemaId("csat", 1)).toBe(`${SCHEMA_NAMESPACE}.csat.v1`);
    expect(schemaId("admin_audit", 2)).toBe(`${SCHEMA_NAMESPACE}.admin_audit.v2`);
  });

  it("rejects malformed names", () => {
    expect(() => schemaId("Csat", 1)).toThrow(/invalid schema name/);
    expect(() => schemaId("csat!", 1)).toThrow(/invalid schema name/);
    expect(() => schemaId("", 1)).toThrow(/invalid schema name/);
  });

  it("rejects non-positive or fractional versions", () => {
    expect(() => schemaId("csat", 0)).toThrow(/invalid schema version/);
    expect(() => schemaId("csat", 1.5)).toThrow(/invalid schema version/);
  });
});
