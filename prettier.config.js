// Единый форматтер для TS/JS/CSS/JSON/YAML/Markdown. Python форматирует ruff.
/** @type {import("prettier").Config} */
export default {
  printWidth: 100,
  singleQuote: true,
  trailingComma: 'all',
  semi: true,
  arrowParens: 'always',
  endOfLine: 'lf',
  overrides: [
    // YAML (compose, pre-commit): двойные кавычки, как принято в docker-документации.
    { files: ['*.yml', '*.yaml'], options: { singleQuote: false } },
  ],
};
