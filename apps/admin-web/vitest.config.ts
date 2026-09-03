import { defineConfig } from "vitest/config";

// The module is pure, typed projection + presentation: it takes the recorded
// `GET /admin/models` payload and returns the tree the page paints. There is
// no DOM to mount and no server to dial, so the suite is a node lane — the
// same shape and the same reason as apps/mobile's e2e specs.
export default defineConfig({
  test: {
    include: ["src/**/*.test.ts", "e2e/**/*.spec.ts"],
    environment: "node",
  },
});
