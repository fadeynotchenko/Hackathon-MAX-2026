// Типизированная обёртка над window.WebApp (MAX Bridge, https://st.max.ru/js/max-web-app.js).
//
// Лист: не знает ни об API, ни о React. Вне MAX (обычный браузер) объекта нет;
// для разработки VITE_DEV_INIT_DATA подставляет подписанный initData
// (python -m scripts.dev_init_data), и вход проходит по-настоящему.

export interface MaxUser {
  id: number;
  first_name: string;
  last_name?: string;
  username?: string;
  language_code?: string;
  photo_url?: string;
}

export interface MaxInitDataUnsafe {
  query_id?: string;
  auth_date?: number;
  hash?: string;
  user?: MaxUser;
  start_param?: string;
  chat?: { id: number; type: string };
}

export type ColorScheme = 'light' | 'dark';
export type Platform = 'ios' | 'android';

// Системная кнопка «Назад» в шапке клиента MAX.
export interface MaxBackButton {
  show?: () => void;
  hide?: () => void;
  onClick?: (handler: () => void) => void;
  offClick?: (handler: () => void) => void;
}

// Подмножество API моста, которым пользуется приложение. Методы объявлены
// опциональными: разные версии клиента MAX отдают разный набор.
export interface MaxWebApp {
  initData: string;
  initDataUnsafe: MaxInitDataUnsafe;
  platform?: string;
  version?: string;
  colorScheme?: ColorScheme;
  ready?: () => void;
  expand?: () => void;
  close?: () => void;
  BackButton?: MaxBackButton;
  HapticFeedback?: {
    impactOccurred?: (style: 'light' | 'medium' | 'heavy') => Promise<unknown> | void;
    notificationOccurred?: (type: 'success' | 'warning' | 'error') => Promise<unknown> | void;
  };
  onEvent?: (event: string, handler: () => void) => void;
  offEvent?: (event: string, handler: () => void) => void;
}

declare global {
  interface Window {
    WebApp?: MaxWebApp;
  }
}

export function getWebApp(): MaxWebApp | null {
  return typeof window !== 'undefined' && window.WebApp ? window.WebApp : null;
}

// initData для входа: из моста, иначе dev-подстановка. Пустая строка — мы не в MAX.
export function getInitData(): string {
  const bridge = getWebApp();
  if (bridge?.initData) return bridge.initData;
  return import.meta.env.VITE_DEV_INIT_DATA ?? '';
}

export function isInsideMax(): boolean {
  return Boolean(getWebApp()?.initData);
}

// Параметр запуска из ссылки ?startapp= или кнопки бота open_app с payload.
export function getStartParam(): string | null {
  return getWebApp()?.initDataUnsafe.start_param || null;
}

export function markReady(): void {
  const bridge = getWebApp();
  bridge?.ready?.();
  bridge?.expand?.();
}

// Вернуться в чат: готовый файл бот уже прислал туда.
export function closeApp(): boolean {
  const close = getWebApp()?.close;
  if (!close) return false;
  close();
  return true;
}

// Вибрации нет в браузере и на десктопе MAX: мост отклоняет промис объектом
// {error: {code: 'client.haptic_feedback_*.request_timeout'}}. Это не ошибка
// приложения, а без перехвата каждое нажатие оставляло Uncaught в консоли.
function quietly(result: Promise<unknown> | void | undefined): void {
  if (result) result.catch(() => undefined);
}

export function haptic(style: 'light' | 'medium' | 'heavy' = 'light'): void {
  quietly(getWebApp()?.HapticFeedback?.impactOccurred?.(style));
}

export function hapticResult(type: 'success' | 'warning' | 'error'): void {
  quietly(getWebApp()?.HapticFeedback?.notificationOccurred?.(type));
}

// Тема клиента. Вне MAX — undefined: провайдер MAX UI возьмёт системную.
export function getColorScheme(): ColorScheme | undefined {
  return getWebApp()?.colorScheme;
}

// Платформа для компонентов MAX UI: они повторяют нативные iOS и Android.
export function getPlatform(): Platform | undefined {
  const platform = getWebApp()?.platform?.toLowerCase();
  if (platform === 'ios') return 'ios';
  if (platform === 'android') return 'android';
  return undefined;
}

// Подписка на смену темы в клиенте (событие themeChanged моста); возвращает отписку.
export function onThemeChange(handler: () => void): () => void {
  const bridge = getWebApp();
  bridge?.onEvent?.('themeChanged', handler);
  return () => bridge?.offEvent?.('themeChanged', handler);
}

// Системная «Назад»: показывается, пока есть обработчик; возвращает отписку.
export function showBackButton(handler: () => void): () => void {
  const button = getWebApp()?.BackButton;
  if (!button) return () => undefined;
  button.onClick?.(handler);
  button.show?.();
  return () => {
    button.offClick?.(handler);
    button.hide?.();
  };
}

// Скрипт моста подключён и в обычном браузере, но кнопку там рисовать некому:
// без initData мы не в клиенте MAX, и «Назад» нужна своя, в шапке экрана.
export function hasBackButton(): boolean {
  return isInsideMax() && Boolean(getWebApp()?.BackButton?.show);
}
