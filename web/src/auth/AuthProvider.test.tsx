import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ApiClient, ApiError } from '@/api/client';
import { useAuth } from './context';
import { AuthProvider } from './AuthProvider';

const session = {
  access_token: 'tok',
  token_type: 'bearer' as const,
  expires_in: 900,
  user: { display_name: 'Ann' } as never,
};

function Probe() {
  const { status, mode, user, error } = useAuth();
  return (
    <div>
      <span data-testid="status">{status}</span>
      <span data-testid="mode">{mode}</span>
      <span data-testid="user">{user?.display_name ?? ''}</span>
      <span data-testid="error">{error ?? ''}</span>
    </div>
  );
}

function renderWith(api: ApiClient) {
  // Живой cookie в тестах нет: refresh отвечает 401, дальше идёт вход по initData.
  vi.spyOn(api, 'refreshSession').mockRejectedValue(
    new ApiError(401, 'auth.refresh.missing', 'Сессия отсутствует', null),
  );
  render(
    <AuthProvider api={api}>
      <Probe />
    </AuthProvider>,
  );
}

afterEach(() => {
  delete window.WebApp;
  vi.unstubAllEnvs();
});

describe('AuthProvider', () => {
  it('logs in with bridge initData inside MAX', async () => {
    window.WebApp = { initData: 'auth_date=1&hash=h', initDataUnsafe: {} };
    const api = new ApiClient({ baseUrl: '' });
    const login = vi.spyOn(api, 'loginMax').mockResolvedValue(session);
    const dev = vi.spyOn(api, 'devInitData');
    renderWith(api);
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('ready'));
    expect(screen.getByTestId('mode')).toHaveTextContent('max');
    expect(screen.getByTestId('user')).toHaveTextContent('Ann');
    expect(login).toHaveBeenCalledWith('auth_date=1&hash=h');
    expect(dev).not.toHaveBeenCalled();
    expect(api.hasToken()).toBe(true);
  });

  it('falls back to the dev endpoint outside MAX in dev mode', async () => {
    vi.stubEnv('VITE_DEV_INIT_DATA', '');
    vi.stubEnv('DEV', true);
    const api = new ApiClient({ baseUrl: '' });
    vi.spyOn(api, 'devInitData').mockResolvedValue({
      init_data: 'dev=1&hash=x',
      max_user_id: 1,
      is_admin: true,
    });
    const login = vi.spyOn(api, 'loginMax').mockResolvedValue(session);
    renderWith(api);
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('ready'));
    expect(screen.getByTestId('mode')).toHaveTextContent('dev');
    expect(login).toHaveBeenCalledWith('dev=1&hash=x');
  });

  it('reports outside when the dev endpoint does not exist', async () => {
    vi.stubEnv('VITE_DEV_INIT_DATA', '');
    vi.stubEnv('DEV', true);
    const api = new ApiClient({ baseUrl: '' });
    vi.spyOn(api, 'devInitData').mockRejectedValue(
      new ApiError(404, 'http.error', 'Not Found', null),
    );
    const login = vi.spyOn(api, 'loginMax');
    renderWith(api);
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('outside'));
    expect(login).not.toHaveBeenCalled();
  });

  it('reports outside immediately in a production build without initData', async () => {
    vi.stubEnv('VITE_DEV_INIT_DATA', '');
    vi.stubEnv('DEV', false);
    const api = new ApiClient({ baseUrl: '' });
    const dev = vi.spyOn(api, 'devInitData');
    renderWith(api);
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('outside'));
    expect(screen.getByTestId('mode')).toHaveTextContent('none');
    expect(dev).not.toHaveBeenCalled();
  });

  it('reuses a live refresh cookie instead of logging in again', async () => {
    window.WebApp = { initData: 'auth_date=1&hash=h', initDataUnsafe: {} };
    const api = new ApiClient({ baseUrl: '' });
    vi.spyOn(api, 'refreshSession').mockResolvedValue(session);
    const login = vi.spyOn(api, 'loginMax');
    render(
      <AuthProvider api={api}>
        <Probe />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('ready'));
    expect(login).not.toHaveBeenCalled();
  });

  it('shows the API error text when login is rejected', async () => {
    window.WebApp = { initData: 'auth_date=1&hash=bad', initDataUnsafe: {} };
    const api = new ApiClient({ baseUrl: '' });
    vi.spyOn(api, 'loginMax').mockRejectedValue(
      new ApiError(401, 'auth.init_data.bad_signature', 'Не удалось подтвердить данные', 'rid'),
    );
    renderWith(api);
    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('error'));
    expect(screen.getByTestId('error')).toHaveTextContent('Не удалось подтвердить данные');
  });
});
