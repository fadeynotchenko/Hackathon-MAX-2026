import { MaxUI } from '@maxhub/max-ui';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import { App } from '@/App';
import { AuthContext, type AuthState } from '@/auth/context';
import type * as webapp from '@/max/webapp';
import { mockApi } from '@/test-utils';

const startParam = vi.hoisted(() => ({ value: null as string | null }));

vi.mock('@/max/webapp', async (importOriginal) => ({
  ...(await importOriginal<typeof webapp>()),
  getStartParam: () => startParam.value,
}));

function LocationProbe() {
  return <span data-testid="location">{useLocation().pathname}</span>;
}

function renderApp(param: string | null) {
  startParam.value = param;
  const auth = {
    status: 'ready',
    mode: 'max',
    user: { id: 1, max_user_id: 100, first_name: 'Анна', is_admin: false },
    error: null,
    api: mockApi(),
    retry: vi.fn(),
  } as unknown as AuthState;
  render(
    <MaxUI colorScheme="light" platform="ios">
      <AuthContext.Provider value={auth}>
        <MemoryRouter initialEntries={['/']}>
          <App />
          <LocationProbe />
        </MemoryRouter>
      </AuthContext.Provider>
    </MaxUI>,
  );
}

describe('App start route', () => {
  it('opens the screen from the bot button instead of the catalog', async () => {
    renderApp('archive');
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/archive'));
    // Корневой редирект на каталог не перебивает кнопку бота и позже.
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(screen.getByTestId('location')).toHaveTextContent('/archive');
  });

  it('opens a document by doc_<id>', async () => {
    renderApp('doc_12');
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/documents/12'));
  });

  it('goes back to the parent screen when the bot opened a screen directly', async () => {
    renderApp('doc_12');
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/documents/12'));
    // Истории под экраном нет: шаг назад по ней ничего бы не сделал.
    fireEvent.click(await screen.findByRole('button', { name: 'Назад' }));
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/archive'));
  });

  it('falls back to the catalog without a start parameter', async () => {
    renderApp(null);
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/create'));
  });
});
