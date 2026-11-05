import js from "@eslint/js";
import globals from "globals";

export default [
  { ignores: ["node_modules/**", ".venv/**", "staticfiles/**", "docs/_build/**"] },
  js.configs.recommended,
  {
    files: ["src/easy_kitchen/static/easy_kitchen/**/*.js"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      globals: globals.browser,
    },
    rules: {
      eqeqeq: ["error", "always"],
      "no-var": "error",
      "prefer-const": "error",
    },
  },
];
