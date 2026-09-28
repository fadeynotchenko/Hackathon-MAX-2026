// Обвязка для тестов экранов: сессия с подменённым API и роутер в памяти.
// Соседние экраны (routes) — для переходов туда и обратно по истории;
// user — поправки к пользователю сессии (например, администратор).
/* eslint-disable react-refresh/only-export-components -- тестовая обвязка, в HMR не участвует */
import { MaxUI } from '@maxhub/max-ui';
import { render } from '@testing-library/react';
import type { ReactElement } from 'react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { vi } from 'vitest';

import { ApiClient, type DocumentView, type Template, type UserProfile } from '@/api/client';
import { ScreenStack } from '@/components/ScreenStack';
import { AuthContext, type AuthState } from '@/auth/context';

export function makeTemplate(overrides: Partial<Template> = {}): Template {
  return {
    id: 1,
    slug: 'invoice',
    title: 'Счёт на оплату',
    kind: 'invoice',
    description: 'Счёт с реквизитами продавца',
    body_format: 'text',
    is_builtin: true,
    in_library: true,
    can_keep: false,
    body: 'Счёт на оплату № {{number}} от {{date}}',
    preview: 'Счёт на оплату № __________ от __________',
    fields: [
      {
        key: 'client_name',
        label: 'Название клиента',
        type: 'text',
        group: 'Клиент',
        required: true,
        hint: '',
        max_length: null,
        carry_over: true,
        today_by_default: false,
        default: '',
      },
      {
        key: 'client_inn',
        label: 'ИНН клиента',
        type: 'inn',
        group: 'Клиент',
        required: false,
        hint: '',
        max_length: null,
        carry_over: true,
        today_by_default: false,
        default: '',
      },
      {
        key: 'total',
        label: 'Сумма к оплате',
        type: 'money',
        group: 'Предмет',
        required: true,
        hint: '',
        max_length: null,
        carry_over: true,
        today_by_default: false,
        default: '',
      },
      {
        key: 'seller_name',
        label: 'Название продавца',
        type: 'text',
        group: 'Продавец',
        required: true,
        hint: '',
        max_length: null,
        carry_over: true,
        today_by_default: false,
        default: '',
      },
    ],
    ...overrides,
  };
}

export function makeDocument(overrides: Partial<DocumentView> = {}): DocumentView {
  return {
    id: 7,
    title: 'Счёт для Альфы',
    status: 'draft',
    template: makeTemplate(),
    counterparty_id: null,
    organization_id: null,
    values: {
      seller_name: {
        value: 'ООО «Мастер»',
        source: 'profile',
        confirmed: true,
        fragment: null,
        confidence: null,
      },
    },
    errors: [],
    missing: ['client_name', 'total'],
    unconfirmed: [],
    ready: false,
    preview: 'Счёт № __________\nПокупатель: __________',
    created_at: '2026-09-24T10:00:00Z',
    updated_at: '2026-09-24T10:00:00Z',
    ...overrides,
  };
}

export function mockApi(): ApiClient {
  return new ApiClient({ baseUrl: '', fetchFn: vi.fn() });
}

function LocationProbe() {
  const location = useLocation();
  return <span data-testid="location">{location.pathname}</span>;
}

export interface ScreenOptions {
  api: ApiClient;
  path: string;
  route: string;
  user?: Partial<UserProfile>;
  routes?: Array<{ path: string; element: ReactElement }>;
}

// Экран сверху стека: скрытые под ним остаются в DOM, и запрос по подписи поля
// нашёл бы одноимённое поле и там.
export function activeScreen(): HTMLElement {
  const found = document.querySelector<HTMLElement>('[data-screen="active"]');
  if (!found) throw new Error('Нет активного экрана');
  return found;
}

export function renderScreen(
  element: ReactElement,
  { api, path, route, user, routes = [] }: ScreenOptions,
) {
  const auth: AuthState = {
    status: 'ready',
    mode: 'dev',
    user: {
      id: 1,
      max_user_id: 100,
      first_name: 'Анна',
      last_name: null,
      username: 'anna',
      display_name: 'Анна',
      language_code: 'ru',
      photo_url: null,
      is_admin: false,
      created_at: '2026-09-01T00:00:00Z',
      last_login_at: null,
      ...user,
    },
    error: null,
    api,
    retry: vi.fn(),
  };
  return render(
    <MaxUI colorScheme="light" platform="ios">
      <AuthContext.Provider value={auth}>
        <MemoryRouter initialEntries={[route]}>
          <ScreenStack>
            {(entry) => (
              <Routes location={entry}>
                <Route path={path} element={element} />
                {routes.map((item) => (
                  <Route key={item.path} path={item.path} element={item.element} />
                ))}
                <Route path="*" element={<span>другой экран</span>} />
              </Routes>
            )}
          </ScreenStack>
          <LocationProbe />
        </MemoryRouter>
      </AuthContext.Provider>
    </MaxUI>,
  );
}
