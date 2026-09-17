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

export interface MaxThemeParams {
  bg_color?: string;
  text_color?: string;
  hint_color?: string;
  link_color?: string;
  button_color?: string;
  button_text_color?: string;
  secondary_bg_color?: string;
}

export interface MaxInitDataUnsafe {
  query_id?: string;
  auth_date?: number;
  hash?: string;
  user?: MaxUser;
  start_param?: string;
  chat?: { id: number; type: string };
}

// Подмножество API моста, которым пользуется приложение. Методы объявлены
// опциональными: разные версии клиента MAX отдают разный набор.
export interface MaxWebApp {
  initData: string;
  initDataUnsafe: MaxInitDataUnsafe;
  platform?: string;
  version?: string;
  colorScheme?: 'light' | 'dark';
  themeParams?: MaxThemeParams;
  ready?: () => void;
  expand?: () => void;
  HapticFeedback?: { impactOccurred: (style: 'light' | 'medium' | 'heavy') => void };
  onEvent?: (event: string, handler: () => void) => void;
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

export function markReady(): void {
  const bridge = getWebApp();
  bridge?.ready?.();
  bridge?.expand?.();
}

export function haptic(style: 'light' | 'medium' | 'heavy' = 'light'): void {
  getWebApp()?.HapticFeedback?.impactOccurred(style);
}

const THEME_VARS: Array<[keyof MaxThemeParams, string]> = [
  ['bg_color', '--max-bg'],
  ['text_color', '--max-text'],
  ['hint_color', '--max-hint'],
  ['link_color', '--max-link'],
  ['button_color', '--max-button'],
  ['button_text_color', '--max-button-text'],
  ['secondary_bg_color', '--max-bg-secondary'],
];

// Цвета темы клиента → CSS-переменные. Дефолты живут в styles/tokens.css,
// поэтому вне MAX страница выглядит как светлая тема.
export function applyTheme(root: HTMLElement = document.documentElement): void {
  const bridge = getWebApp();
  const params = bridge?.themeParams ?? {};
  for (const [key, cssVar] of THEME_VARS) {
    const value = params[key];
    if (value) root.style.setProperty(cssVar, value);
  }
  root.dataset['colorScheme'] = bridge?.colorScheme ?? 'light';
}

// Тема применяется при старте и при смене в клиенте (событие themeChanged моста).
export function watchTheme(root: HTMLElement = document.documentElement): void {
  applyTheme(root);
  getWebApp()?.onEvent?.('themeChanged', () => applyTheme(root));
}
