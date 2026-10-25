// Сессия мини-аппа: вход по initData при старте, refresh на 401, выход.
//
// Откуда берётся initData (по убыванию приоритета):
//   1. window.WebApp.initData — запуск внутри клиента MAX;
//   2. VITE_DEV_INIT_DATA — production-сборка, открытая в браузере разработчика;
//   3. GET /api/v1/dev/init-data — vite dev-server: ручка есть только вне production,
//      поэтому на локали мини-апп входит сам, без ручной генерации.
// Ничего из этого нет — статус outside («откройте в MAX»).
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';

import { ApiClient, ApiError } from '@/api/client';
import type { SessionResponse, UserProfile } from '@/api/client';
import { getInitData, isInsideMax, markReady } from '@/max/webapp';

import { AuthContext, type AuthMode, type AuthState, type AuthStatus } from './context';

export interface AuthProviderProps {
  children: ReactNode;
  api?: ApiClient;
}

function initialMode(): AuthMode {
  if (isInsideMax()) return 'max';
  if (getInitData() || import.meta.env.DEV) return 'dev';
  return 'none';
}

export function AuthProvider({ children, api: injectedApi }: AuthProviderProps) {
  const [mode] = useState<AuthMode>(initialMode);
  const [status, setStatus] = useState<AuthStatus>(() => (mode === 'none' ? 'outside' : 'loading'));
  const [user, setUser] = useState<UserProfile | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Один вход на все запуски эффекта: StrictMode в dev монтирует эффект дважды,
  // и без этого в API уходили бы два параллельных /auth/max.
  const loginInFlight = useRef<Promise<SessionResponse> | null>(null);

  const api = useMemo(
    () =>
      injectedApi ??
      new ApiClient({
        // Refresh не прошёл (cookie заблокирована во фрейме или истекла). Внутри
        // MAX и в dev initData всегда под рукой — просто входим заново.
        onSessionLost: () => {
          setUser(null);
          if (mode === 'none') {
            setError('Сессия истекла, откройте приложение заново');
            setStatus('error');
            return;
          }
          setStatus('loading');
        },
      }),
    [injectedApi, mode],
  );

  // Клиент MAX держит свой лоадер, пока не получит ready(): снимаем его сразу,
  // иначе экраны ошибки и «откройте в MAX» остались бы за ним.
  useEffect(() => {
    markReady();
  }, []);

  // Вход выполняется, пока статус loading; retry возвращает его в loading.
  useEffect(() => {
    if (status !== 'loading') return;
    let cancelled = false;
    const initData = getInitData();
    if (!loginInFlight.current) {
      // Лениво: при живой cookie dev-ручку незачем звать вовсе.
      const source = () =>
        initData
          ? Promise.resolve(initData)
          : api.devInitData().then((response) => response.init_data);
      // Внутри MAX — сразу вход по initData: клиент не доносит refresh-cookie до
      // следующего запуска (на проде 122 из 123 открытий начинались с 401 на
      // /auth/refresh), и проба только задерживала первый экран. В браузере
      // сначала живая cookie — без новой семьи токенов при каждом открытии.
      const login = () => source().then((data) => api.loginMax(data));
      loginInFlight.current = (
        mode === 'max' ? login() : api.refreshSession().catch(login)
      ).finally(() => {
        loginInFlight.current = null;
      });
    }
    loginInFlight.current
      .then((session) => {
        if (cancelled) return;
        api.setAccessToken(session.access_token);
        setUser(session.user);
        setStatus('ready');
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        // Dev-ручки нет (production-сборка вне MAX) — это не ошибка, а «откройте в MAX».
        if (!initData && err instanceof ApiError && err.status === 404) {
          setStatus('outside');
          return;
        }
        setError(err instanceof ApiError ? err.message : 'Сервер недоступен');
        setStatus('error');
      });
    return () => {
      cancelled = true;
    };
  }, [api, mode, status]);

  const retry = useCallback(() => {
    setError(null);
    setStatus('loading');
  }, []);

  const value = useMemo<AuthState>(
    () => ({ status, mode, user, error, api, retry }),
    [status, mode, user, error, api, retry],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
