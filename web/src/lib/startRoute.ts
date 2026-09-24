// Параметр запуска (кнопка бота или ссылка ?startapp=) → экран. Неизвестное
// значение открывает главный экран, а не ошибку.
export function startRoute(param: string | null): string | null {
  if (!param) return null;
  if (param === 'create' || param === 'archive' || param === 'profile') return `/${param}`;
  if (param === 'company') return '/profile/organizations';
  const doc = /^doc_(\d+)$/.exec(param);
  if (doc) return `/documents/${doc[1]}`;
  return null;
}
