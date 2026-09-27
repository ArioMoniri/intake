import { defineConfig } from "vitest/config";

// The modules are pure, typed projection + presentation: each takes a recorded
// `GET /admin/*` payload and returns the tree the page paints. The ops console
// (INT-351) adds the rendered page itself, and the spec renders that React tree
// to static markup — still no DOM to mount and no server to dial, so the suite
// stays a node lane, the same shape and the same reason as apps/mobile's specs.
export default defineConfig({
  oxc: { jsx: { runtime: "automatic" } },
  test: {
    include: ["src/**/*.test.ts", "src/**/*.test.tsx", "e2e/**/*.spec.ts"],
    environment: "node",
  },
});
