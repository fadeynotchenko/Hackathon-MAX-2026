import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  getColorScheme,
  getInitData,
  getPlatform,
  getStartParam,
  isInsideMax,
  markReady,
  onThemeChange,
  showBackButton,
} from './webapp';

afterEach(() => {
  delete window.WebApp;
});

describe('webapp bridge', () => {
  it('reports outside MAX when the bridge is missing', () => {
    vi.stubEnv('VITE_DEV_INIT_DATA', '');
    expect(isInsideMax()).toBe(false);
    expect(getInitData()).toBe('');
    expect(getStartParam()).toBeNull();
    expect(getColorScheme()).toBeUndefined();
    vi.unstubAllEnvs();
  });

  it('uses bridge initData and calls ready/expand', () => {
    let ready = 0;
    let expanded = 0;
    window.WebApp = {
      initData: 'auth_date=1&hash=x',
      initDataUnsafe: { start_param: 'archive' },
      ready: () => {
        ready += 1;
      },
      expand: () => {
        expanded += 1;
      },
    };
    expect(isInsideMax()).toBe(true);
    expect(getInitData()).toBe('auth_date=1&hash=x');
    expect(getStartParam()).toBe('archive');
    markReady();
    expect(ready).toBe(1);
    expect(expanded).toBe(1);
  });

  it('reads platform and color scheme for MAX UI', () => {
    window.WebApp = { initData: '', initDataUnsafe: {}, platform: 'iOS', colorScheme: 'dark' };
    expect(getPlatform()).toBe('ios');
    expect(getColorScheme()).toBe('dark');
    window.WebApp.platform = 'web';
    expect(getPlatform()).toBeUndefined();
  });

  it('subscribes and unsubscribes theme changes', () => {
    const handlers = new Map<string, () => void>();
    window.WebApp = {
      initData: '',
      initDataUnsafe: {},
      onEvent: (event, handler) => handlers.set(event, handler),
      offEvent: (event) => handlers.delete(event),
    };
    const handler = vi.fn();
    const off = onThemeChange(handler);
    handlers.get('themeChanged')?.();
    expect(handler).toHaveBeenCalledTimes(1);
    off();
    expect(handlers.has('themeChanged')).toBe(false);
  });

  it('shows the native back button while a handler is attached', () => {
    const show = vi.fn();
    const hide = vi.fn();
    let attached: (() => void) | null = null;
    window.WebApp = {
      initData: '',
      initDataUnsafe: {},
      BackButton: {
        show,
        hide,
        onClick: (handler) => {
          attached = handler;
        },
        offClick: () => {
          attached = null;
        },
      },
    };
    const back = vi.fn();
    const off = showBackButton(back);
    expect(show).toHaveBeenCalled();
    attached!();
    expect(back).toHaveBeenCalled();
    off();
    expect(hide).toHaveBeenCalled();
    expect(attached).toBeNull();
  });
});
