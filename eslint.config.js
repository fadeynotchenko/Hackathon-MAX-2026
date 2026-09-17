// ESLint flat-config для обоих TS-воркспейсов (bot/ — Node, web/ — React 19).
//
//   pnpm lint          # проверка
//   pnpm lint:fix      # автофиксы
//
// Type-aware правила (no-floating-promises, no-misused-promises) включены:
// в боте и в мини-аппе необработанный промис — это молча потерянная ошибка.
import js from '@eslint/js';
import prettier from 'eslint-config-prettier';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import globals from 'globals';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  {
    ignores: [
      '**/dist/**',
      '**/node_modules/**',
      '**/coverage/**',
      'web/src/api/schema.d.ts',
      'core/**',
      '**/.venv/**',
      '**/.cache/**',
      '**/.pnpm-store/**',
      'app_logs/**',
      'app_logs/**',
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommendedTypeChecked,
  {
    languageOptions: {
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    rules: {
      '@typescript-eslint/no-explicit-any': 'error',
      '@typescript-eslint/consistent-type-imports': ['error', { prefer: 'type-imports' }],
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_', caughtErrorsIgnorePattern: '^_' },
      ],
      '@typescript-eslint/no-floating-promises': 'error',
      '@typescript-eslint/no-misused-promises': ['error', { checksVoidReturn: false }],
      // Комментарии-заглушки вида TODO/FIXME без ссылки на задачу — это долг,
      // который никто не вернёт. Либо делаем, либо пишем `TODO(#123)`.
      'no-warning-comments': ['error', { terms: ['todo', 'fixme', 'xxx'], location: 'start' }],
      eqeqeq: ['error', 'always'],
      'no-console': 'error',
    },
  },
  {
    // Конфиги инструментов запускаются Node вне tsconfig — без type-aware правил.
    files: ['**/*.js', '**/*.cjs', '**/*.mjs', '**/*.config.ts'],
    ...tseslint.configs.disableTypeChecked,
    languageOptions: {
      ...tseslint.configs.disableTypeChecked.languageOptions,
      globals: { ...globals.node },
    },
  },
  {
    files: ['bot/**/*.ts'],
    languageOptions: { globals: { ...globals.node } },
  },
  {
    files: ['web/**/*.{ts,tsx}'],
    languageOptions: { globals: { ...globals.browser } },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
    },
  },
  {
    // В тестах заглушки часто объявляются async ради сигнатуры, без await внутри.
    files: ['**/*.test.{ts,tsx}', '**/test-setup.ts'],
    rules: {
      'no-console': 'off',
      '@typescript-eslint/require-await': 'off',
      '@typescript-eslint/no-unsafe-assignment': 'off',
      '@typescript-eslint/no-unsafe-member-access': 'off',
    },
  },
  prettier,
);
