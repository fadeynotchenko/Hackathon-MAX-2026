import { afterEach, describe, expect, it, vi } from 'vitest';

import { applyTheme, getInitData, isInsideMax, markReady, watchTheme } from './webapp';

afterEach(() => {
  delete window.WebApp;
});

describe('webapp bridge', () => {
  it('reports outside MAX when the bridge is missing', () => {
    vi.stubEnv('VITE_DEV_INIT_DATA', '');
    expect(isInsideMax()).toBe(false);
    expect(getInitData()).toBe('');
    vi.unstubAllEnvs();
  });

  it('uses bridge initData and calls ready/expand', () => {
    let ready = 0;
    let expanded = 0;
    window.WebApp = {
      initData: 'auth_date=1&hash=x',
      initDataUnsafe: {},
      ready: () => {
        ready += 1;
      },
      expand: () => {
        expanded += 1;
      },
    };
    expect(isInsideMax()).toBe(true);
    expect(getInitData()).toBe('auth_date=1&hash=x');
    markReady();
    expect(ready).toBe(1);
    expect(expanded).toBe(1);
  });

  it('re-applies the theme when the bridge reports a change', () => {
    const handlers: Record<string, () => void> = {};
    window.WebApp = {
      initData: '',
      initDataUnsafe: {},
      colorScheme: 'light',
      themeParams: { bg_color: '#ffffff' },
      onEvent: (event, handler) => {
        handlers[event] = handler;
      },
    };
    const root = document.createElement('div');
    watchTheme(root);
    expect(root.dataset['colorScheme']).toBe('light');
    window.WebApp.colorScheme = 'dark';
    handlers['themeChanged']?.();
    expect(root.dataset['colorScheme']).toBe('dark');
  });

  it('maps theme params to css variables', () => {
    window.WebApp = {
      initData: '',
      initDataUnsafe: {},
      colorScheme: 'dark',
      themeParams: { bg_color: '#000000', text_color: '#ffffff' },
    };
    const root = document.createElement('div');
    applyTheme(root);
    expect(root.style.getPropertyValue('--max-bg')).toBe('#000000');
    expect(root.style.getPropertyValue('--max-text')).toBe('#ffffff');
    expect(root.dataset['colorScheme']).toBe('dark');
  });
});
