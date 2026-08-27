import { defineConfig } from "vitest/config";

// Coverage floor per scripts/ci/coverage_thresholds.yaml (ts.default) —
// CLAUDE.md invariant 8: thresholds only rise.
export default defineConfig({
  test: {
    coverage: {
      enabled: true,
      provider: "v8",
      include: ["src/**"],
      thresholds: { lines: 85, functions: 85, branches: 85, statements: 85 },
    },
  },
});
