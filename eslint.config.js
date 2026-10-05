import js from "@eslint/js";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["custom_components/**", "node_modules/**"] },
  js.configs.recommended,
  ...tseslint.configs.strict,
  {
    rules: {
      "no-restricted-properties": [
        "error",
        { property: "innerHTML", message: "Use h() so text is never parsed as HTML." },
        { property: "outerHTML", message: "Use h() so text is never parsed as HTML." },
      ],
    },
  },
);
