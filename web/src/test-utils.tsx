// Обвязка для тестов экранов: сессия с подменённым API и роутер в памяти.
/* eslint-disable react-refresh/only-export-components -- тестовая обвязка, в HMR не участвует */
import { MaxUI } from '@maxhub/max-ui';
import { render } from '@testing-library/react';
import type { ReactElement } from 'react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { vi } from 'vitest';

import { ApiClient, type DocumentView, type Template } from '@/api/client';
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

export function renderScreen(
  element: ReactElement,
  { api, path, route }: { api: ApiClient; path: string; route: string },
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
    },
    error: null,
    api,
    logout: vi.fn(),
    retry: vi.fn(),
  };
  return render(
    <MaxUI colorScheme="light" platform="ios">
      <AuthContext.Provider value={auth}>
        <MemoryRouter initialEntries={[route]}>
          <Routes>
            <Route path={path} element={element} />
            <Route path="*" element={<span>другой экран</span>} />
          </Routes>
          <LocationProbe />
        </MemoryRouter>
      </AuthContext.Provider>
    </MaxUI>,
  );
}
