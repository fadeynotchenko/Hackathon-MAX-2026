// HTTP-клиент API мини-аппа. Единственное место, где живёт fetch.
//
// Access-токен хранится в памяти (не в localStorage: XSS-утечка токена
// ограничена временем жизни вкладки), refresh — в httpOnly-cookie, которую
// ставит бэкенд. На 401 клиент один раз пробует /auth/refresh и повторяет
// запрос; параллельные 401 ждут одного и того же refresh-промиса.
import type { components } from './schema';

export type ErrorResponse = components['schemas']['ErrorResponse'];
export type SessionResponse = components['schemas']['SessionResponse'];
export type UserProfile = components['schemas']['UserProfileSchema'];
export type AdminStats = components['schemas']['AdminStatsResponse'];
export type NotifyRequest = components['schemas']['NotifyRequest'];
export type NotifyResponse = components['schemas']['NotifyResponse'];
export type DevInitDataResponse = components['schemas']['DevInitDataResponse'];

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly requestId: string | null,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export interface ApiClientOptions {
  baseUrl?: string;
  fetchFn?: typeof fetch;
  onSessionLost?: () => void;
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  body?: unknown;
  auth?: boolean;
  retryOn401?: boolean;
}

export class ApiClient {
  private accessToken: string | null = null;
  private refreshing: Promise<boolean> | null = null;
  private readonly baseUrl: string;
  private readonly fetchFn: typeof fetch;
  private readonly onSessionLost: (() => void) | undefined;

  constructor(options: ApiClientOptions = {}) {
    this.baseUrl = (options.baseUrl ?? import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '');
    this.fetchFn = options.fetchFn ?? ((input, init) => fetch(input, init));
    this.onSessionLost = options.onSessionLost;
  }

  setAccessToken(token: string | null): void {
    this.accessToken = token;
  }

  hasToken(): boolean {
    return this.accessToken !== null;
  }

  async request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    const { method = 'GET', body, auth = true, retryOn401 = true } = options;
    const headers: Record<string, string> = { Accept: 'application/json' };
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    if (auth && this.accessToken) headers['Authorization'] = `Bearer ${this.accessToken}`;

    const response = await this.fetchFn(`${this.baseUrl}${path}`, {
      method,
      headers,
      credentials: 'include',
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    });

    if (response.status === 401 && auth && retryOn401 && (await this.refresh())) {
      return this.request<T>(path, { ...options, retryOn401: false });
    }
    if (!response.ok) throw await this.toError(response);
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  }

  // Один refresh на все параллельные 401: второй вызов ждёт первый.
  private refresh(): Promise<boolean> {
    if (!this.refreshing) {
      this.refreshing = this.doRefresh().finally(() => {
        this.refreshing = null;
      });
    }
    return this.refreshing;
  }

  private async doRefresh(): Promise<boolean> {
    try {
      const session = await this.request<SessionResponse>('/api/v1/auth/refresh', {
        method: 'POST',
        auth: false,
      });
      this.accessToken = session.access_token;
      return true;
    } catch (err) {
      // Сессии больше нет только если API так сказал. Сеть, 502 или таймаут —
      // временная беда, токен в памяти остаётся, исходный запрос вернёт ошибку.
      if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
        this.accessToken = null;
        this.onSessionLost?.();
      }
      return false;
    }
  }

  private async toError(response: Response): Promise<ApiError> {
    let payload: Partial<ErrorResponse> = {};
    try {
      payload = (await response.json()) as Partial<ErrorResponse>;
    } catch {
      // Тело не JSON (nginx 502/504): оставляем статус и generic-текст.
    }
    const detail =
      typeof payload.detail === 'string' ? payload.detail : `Ошибка запроса (${response.status})`;
    return new ApiError(
      response.status,
      payload.code ?? 'http.error',
      detail,
      payload.request_id ?? null,
    );
  }

  // Типизированные ручки. Пути совпадают с operation_id в OpenAPI.
  loginMax(initData: string): Promise<SessionResponse> {
    return this.request<SessionResponse>('/api/v1/auth/max', {
      method: 'POST',
      body: { init_data: initData },
      auth: false,
      retryOn401: false,
    });
  }

  refreshSession(): Promise<SessionResponse> {
    return this.request<SessionResponse>('/api/v1/auth/refresh', {
      method: 'POST',
      auth: false,
      retryOn401: false,
    });
  }

  logout(): Promise<void> {
    return this.request<void>('/api/v1/auth/logout', { method: 'POST', retryOn401: false });
  }

  me(): Promise<UserProfile> {
    return this.request<UserProfile>('/api/v1/me');
  }

  // Существует только вне production: в проде отвечает 404.
  devInitData(): Promise<DevInitDataResponse> {
    return this.request<DevInitDataResponse>('/api/v1/dev/init-data', {
      auth: false,
      retryOn401: false,
    });
  }

  adminStats(): Promise<AdminStats> {
    return this.request<AdminStats>('/api/v1/admin/stats');
  }

  adminNotify(body: NotifyRequest): Promise<NotifyResponse> {
    return this.request<NotifyResponse>('/api/v1/admin/notify', { method: 'POST', body });
  }
}
