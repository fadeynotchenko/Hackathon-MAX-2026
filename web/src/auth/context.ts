// Контекст сессии. Отдельный файл от провайдера: fast refresh требует, чтобы
// модуль с компонентом экспортировал только компоненты.
import { createContext, useContext } from 'react';

import type { ApiClient, UserProfile } from '@/api/client';

export type AuthStatus = 'loading' | 'ready' | 'outside' | 'error' | 'signed_out';
// Откуда пришёл initData: из клиента MAX, из VITE_DEV_INIT_DATA/dev-ручки, или его нет.
export type AuthMode = 'max' | 'dev' | 'none';

export interface AuthState {
  status: AuthStatus;
  mode: AuthMode;
  user: UserProfile | null;
  error: string | null;
  api: ApiClient;
  logout: () => Promise<void>;
  retry: () => void;
}

export const AuthContext = createContext<AuthState | null>(null);

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth вне AuthProvider');
  return ctx;
}
