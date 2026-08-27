import { defineConfig } from "vitest/config";
import { fileURLToPath } from "node:url";

// Unit tests cover the pure modules (theme, i18n, session rules, fixtures)
// plus the static nav-map spec in e2e/. Component rendering is exercised via
// Expo tooling, not vitest — no jsdom needed.
export default defineConfig({
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  test: {
    include: ["src/**/*.test.ts", "e2e/**/*.spec.ts"],
    environment: "node",
  },
});
