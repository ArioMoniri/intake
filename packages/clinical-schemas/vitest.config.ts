import { defineConfig } from "vitest/config";

// Coverage floor per scripts/ci/coverage_thresholds.yaml (ts.default) —
// CLAUDE.md invariant 8: thresholds only rise.
export default defineConfig({
  test: {
    coverage: {
      enabled: true,
      provider: "v8",
      // Vitest 4 dropped `coverage.extension`, so a bare "src/**" now also
      // matches the Python package and its .pyc files that share src/. Naming
      // *.ts keeps exactly the set Vitest 3 measured (INT-346).
      include: ["src/**/*.ts"],
      thresholds: { lines: 85, functions: 85, branches: 85, statements: 85 },
    },
  },
});
