import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    ignores: ["**/dist/**", "**/node_modules/**", "files/**"],
  },
  ...tseslint.configs.recommended,
  {
    rules: {
      // 07 §1: `text-transform` and Turkish-hostile casing are handled at the
      // component layer; the lint rules for them arrive with the mobile issues.
      "@typescript-eslint/explicit-module-boundary-types": "error",
    },
  },
);
