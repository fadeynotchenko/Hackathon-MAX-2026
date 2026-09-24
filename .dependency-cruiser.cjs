// Архитектурные контракты TS-части (аналог .importlinter для Python).
//
//   pnpm depcruise
//
// Проверяется в pre-commit, в Stop-хуке Claude Code и в CI. Нарушение —
// ошибка, а не предупреждение: контракт, который можно проигнорировать,
// перестаёт быть контрактом.
/** @type {import('dependency-cruiser').IConfiguration} */
module.exports = {
  forbidden: [
    {
      name: 'no-circular',
      severity: 'error',
      comment: 'Циклы между модулями — источник undefined при импорте и неявных связей.',
      from: {},
      to: { circular: true },
    },
    {
      name: 'bot-and-web-independent',
      severity: 'error',
      comment:
        'Бот и мини-апп — разные процессы с разными рантаймами (Node и браузер). ' +
        'Общий код между ними — это контракт API, а не импорт.',
      from: { path: '^bot/src' },
      to: { path: '^web/src' },
    },
    {
      name: 'web-and-bot-independent',
      severity: 'error',
      from: { path: '^web/src' },
      to: { path: '^bot/src' },
    },
    {
      name: 'services-share-only-contracts',
      severity: 'error',
      comment:
        'Сервисы репозитория (core, bot, web) не импортируют исходники друг друга: ' +
        'общее между ними — только артефакты в contracts/.',
      from: { path: '^(bot|web)/src' },
      to: { path: '^core/' },
    },
    {
      name: 'bot-infra-not-into-handlers',
      severity: 'error',
      comment:
        'Инфраструктура бота (конфиг, логгер, сессии, события) не знает о хендлерах: ' +
        'зависимости направлены от сценариев к инфраструктуре, не наоборот.',
      from: { path: '^bot/src/(config|logger|redis|context|session|events|health|middlewares)' },
      to: { path: '^bot/src/(handlers|keyboards)' },
    },
    {
      name: 'web-max-bridge-is-leaf',
      severity: 'error',
      comment:
        'web/src/max — обёртка над window.WebApp. Это лист: не тянет ни API-клиент, ' +
        'ни страницы, иначе её нельзя ни переиспользовать, ни тестировать отдельно.',
      from: { path: '^web/src/max' },
      to: { path: '^web/src/(api|pages|auth|components)' },
    },
    {
      name: 'web-api-client-is-transport',
      severity: 'error',
      comment: 'API-клиент — транспорт. Он не знает о React-дереве.',
      from: { path: '^web/src/api' },
      to: { path: '^web/src/(pages|components|auth)' },
    },
    {
      name: 'not-to-dev-dep',
      severity: 'error',
      comment: 'Прод-код не импортирует devDependencies — в образе их нет.',
      from: {
        path: '^(bot|web)/src',
        pathNot: [
          '\\.test\\.(ts|tsx)$',
          '\\.d\\.ts$',
          '(^|/)test-setup\\.ts$',
          '(^|/)test-utils\\.tsx?$',
        ],
      },
      to: { dependencyTypes: ['npm-dev'], dependencyTypesNot: ['type-only'] },
    },
    {
      name: 'not-to-unresolvable',
      severity: 'error',
      from: {},
      to: { couldNotResolve: true },
    },
    {
      name: 'no-orphans',
      severity: 'warn',
      comment: 'Файл, который никто не импортирует, — либо мёртвый код, либо забытый entrypoint.',
      from: {
        orphan: true,
        pathNot: [
          '\\.d\\.ts$',
          '\\.test\\.(ts|tsx)$',
          '(^|/)test-utils\\.tsx?$',
          '(^|/)main\\.tsx?$',
          'vite-env\\.d\\.ts$',
        ],
      },
      to: {},
    },
  ],
  options: {
    doNotFollow: { path: 'node_modules' },
    exclude: { path: '\\.test\\.(ts|tsx)$|/dist/' },
    tsPreCompilationDeps: true,
    // Корневой tsconfig.json существует ради инструментов: алиас `@/` → web/src.
    tsConfig: { fileName: 'tsconfig.json' },
    enhancedResolveOptions: {
      exportsFields: ['exports'],
      conditionNames: ['import', 'require', 'node', 'default', 'types'],
      mainFields: ['module', 'main', 'types', 'typings'],
    },
    reporterOptions: { text: { highlightFocused: true } },
  },
};
