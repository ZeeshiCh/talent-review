import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTypeScript from "eslint-config-next/typescript";

export default defineConfig([
  ...nextVitals,
  ...nextTypeScript,
  {
    settings: { next: { rootDir: "apps/web/" } },
  },
  {
    files: [
      "apps/web/src/hooks/use-candidate-interview.ts",
      "apps/web/src/hooks/use-hr-review-data.ts",
    ],
    // These hooks deliberately reset drafts and loading flags while synchronizing
    // native URL/server state. Async completions are guarded against stale reads.
    rules: { "react-hooks/set-state-in-effect": "off" },
  },
  globalIgnores([
    "**/node_modules/**",
    "**/.next/**",
    "**/out/**",
    "**/build/**",
    "**/dist/**",
    "**/.venv/**",
    "**/__pycache__/**",
    "**/.pytest_cache/**",
    "**/.ruff_cache/**",
    "**/next-env.d.ts",
    "var/**",
    "work/**",
  ]),
]);
