// INT-019 — the eslint-security half of the SAST gate (invariant 14:
// "ESLint security rules" in files/10 §8).
//
// WHY IT IS A SEPARATE CONFIG. The workspace lint (`pnpm -r lint`, run by
// ci.yml's check-ts) is the code-quality pass and its config belongs to the
// workspace. This one is a security pass with a different owner, a different
// severity policy and a different failure meaning, and it is run by
// scripts/ci/eslint_security.sh from `make security` and the security
// workflow. Keeping them apart means a lint-rule discussion cannot quietly
// disable a security rule.
//
// WHY THE PLUGIN IS NOT A WORKSPACE DEPENDENCY. eslint-plugin-security is
// installed, pinned, into .cache/eslint-security/ by the runner script rather
// than added to the root package.json: the lockfile is shared with several
// in-flight branches, and a lockfile conflict is a bad reason for a security
// gate to be unavailable. The pin lives in one place — ESLINT_SECURITY_VERSION
// in scripts/ci/eslint_security.sh — and the gate fails closed if the install
// did not happen.
//
// `basePath` is what lets a config file under scripts/ci/ address the whole
// repository: without it, every pattern here would resolve against scripts/ci.
import security from "../../.cache/eslint-security/node_modules/eslint-plugin-security/index.js";
import tseslint from "typescript-eslint";

const recommended = Object.keys(security.configs.recommended.rules);

export default [
  {
    basePath: "../..",
    ignores: [
      "**/node_modules/**",
      "**/dist/**",
      "**/build/**",
      "**/.expo/**",
      "**/coverage/**",
      // the historical record, not code
      "files/**",
    ],
  },
  {
    basePath: "../..",
    files: ["**/*.{js,mjs,cjs,jsx,ts,tsx}"],
    languageOptions: {
      // typescript-eslint's parser comes from the workspace devDependencies;
      // without it every .ts file is a parse error rather than a scan.
      parser: tseslint.parser,
      ecmaVersion: "latest",
      sourceType: "module",
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    plugins: { security },
    // Every recommended rule at `error`. Nothing is downgraded to a warning:
    // a warning in a security gate is a finding nobody reads. What keeps the
    // gate green on a tree that predates it is the baseline in
    // eslint_security_baseline.json, which may only shrink — not a lowered
    // severity and not a disabled rule.
    rules: Object.fromEntries(recommended.map((rule) => [rule, "error"])),
  },
];
