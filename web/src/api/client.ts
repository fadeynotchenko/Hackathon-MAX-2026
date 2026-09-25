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
export type AdminMetrics = components['schemas']['AdminMetricsResponse'];
export type DailyMetrics = components['schemas']['DailyMetricsSchema'];
export type NotifyRequest = components['schemas']['NotifyRequest'];
export type NotifyResponse = components['schemas']['NotifyResponse'];
export type DevInitDataResponse = components['schemas']['DevInitDataResponse'];
export type Template = components['schemas']['TemplateSchema'];
export type FieldSpec = components['schemas']['FieldSpecSchema'];
export type FieldType = components['schemas']['FieldType'];
export type FieldValue = components['schemas']['FieldValueSchema'];
export type FieldError = components['schemas']['FieldErrorSchema'];
export type ValueSource = components['schemas']['ValueSource'];
export type DocumentView = components['schemas']['DocumentSchema'];
export type DocumentSummary = components['schemas']['DocumentSummarySchema'];
export type DocumentFact = components['schemas']['DocumentFactSchema'];
export type DocumentFile = components['schemas']['DocumentFileSchema'];
export type Organization = components['schemas']['OrganizationSchema'];
export type OrganizationRequest = components['schemas']['OrganizationRequest'];
export type Counterparty = components['schemas']['CounterpartySchema'];
export type CounterpartyRequest = components['schemas']['CounterpartyRequest'];
export type RecognizedRequisites = components['schemas']['RecognizedRequisitesSchema'];
export type AgentFillResponse = components['schemas']['AgentFillResponse'];
export type SendDocumentResponse = components['schemas']['SendDocumentResponse'];
export type FileFormat = 'pdf' | 'docx';

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
  // Файл уходит сырым телом с его Content-Type (фото, скан, голосовое), а не JSON.
  file?: Blob;
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
    const { method = 'GET', body, file, auth = true, retryOn401 = true } = options;
    const headers: Record<string, string> = { Accept: 'application/json' };
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    if (file !== undefined) headers['Content-Type'] = file.type || 'application/octet-stream';
    if (auth && this.accessToken) headers['Authorization'] = `Bearer ${this.accessToken}`;

    const payload = file ?? (body !== undefined ? JSON.stringify(body) : undefined);
    const response = await this.fetchFn(`${this.baseUrl}${path}`, {
      method,
      headers,
      credentials: 'include',
      ...(payload !== undefined ? { body: payload } : {}),
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

  adminMetrics(days: number): Promise<AdminMetrics> {
    return this.request<AdminMetrics>(`/api/v1/admin/metrics?days=${days}`);
  }

  adminNotify(body: NotifyRequest): Promise<NotifyResponse> {
    return this.request<NotifyResponse>('/api/v1/admin/notify', { method: 'POST', body });
  }

  // Шаблоны и документы.
  templates(): Promise<Template[]> {
    return this.request<Template[]>('/api/v1/templates');
  }

  template(templateId: number): Promise<Template> {
    return this.request<Template>(`/api/v1/templates/${templateId}`);
  }

  documents(): Promise<DocumentSummary[]> {
    return this.request<DocumentSummary[]>('/api/v1/documents');
  }

  document(documentId: number): Promise<DocumentView> {
    return this.request<DocumentView>(`/api/v1/documents/${documentId}`);
  }

  createDocument(body: {
    template_id: number;
    counterparty_id?: number | null;
    organization_id?: number | null;
    title?: string;
  }): Promise<DocumentView> {
    return this.request<DocumentView>('/api/v1/documents', { method: 'POST', body });
  }

  // Только то, что человек поменял: значение, прошедшее через форму без правки,
  // сохранило бы источник «вручную» вместо «из профиля» или «из карточки».
  setFields(documentId: number, values: Record<string, string>): Promise<DocumentView> {
    const body = {
      values: Object.fromEntries(Object.entries(values).map(([key, value]) => [key, { value }])),
    };
    return this.request<DocumentView>(`/api/v1/documents/${documentId}/fields`, {
      method: 'PATCH',
      body,
    });
  }

  confirmFields(documentId: number, keys: string[] | null = null): Promise<DocumentView> {
    return this.request<DocumentView>(`/api/v1/documents/${documentId}/confirm`, {
      method: 'POST',
      body: { keys },
    });
  }

  recognizeIntoDocument(documentId: number, file: Blob, hint?: string): Promise<AgentFillResponse> {
    const query = hint ? `?hint=${encodeURIComponent(hint)}` : '';
    return this.request<AgentFillResponse>(
      `/api/v1/documents/${documentId}/agent/recognize${query}`,
      { method: 'POST', file },
    );
  }

  coverLetter(documentId: number): Promise<{ text: string }> {
    return this.request<{ text: string }>(`/api/v1/documents/${documentId}/agent/cover-letter`, {
      method: 'POST',
    });
  }

  sendDocument(
    documentId: number,
    format: FileFormat,
    text: string | null,
  ): Promise<SendDocumentResponse> {
    return this.request<SendDocumentResponse>(`/api/v1/documents/${documentId}/send`, {
      method: 'POST',
      body: { format, text },
    });
  }

  copyDocument(documentId: number): Promise<DocumentView> {
    return this.request<DocumentView>(`/api/v1/documents/${documentId}/copy`, {
      method: 'POST',
      body: { title: null },
    });
  }

  deleteDocument(documentId: number): Promise<void> {
    return this.request<void>(`/api/v1/documents/${documentId}`, { method: 'DELETE' });
  }

  documentHistory(documentId: number): Promise<DocumentFact[]> {
    return this.request<DocumentFact[]>(`/api/v1/documents/${documentId}/history`);
  }

  // Реквизиты сторон.
  organizations(): Promise<Organization[]> {
    return this.request<Organization[]>('/api/v1/organizations');
  }

  createOrganization(body: OrganizationRequest): Promise<Organization> {
    return this.request<Organization>('/api/v1/organizations', { method: 'POST', body });
  }

  updateOrganization(organizationId: number, body: OrganizationRequest): Promise<Organization> {
    return this.request<Organization>(`/api/v1/organizations/${organizationId}`, {
      method: 'PUT',
      body,
    });
  }

  deleteOrganization(organizationId: number): Promise<void> {
    return this.request<void>(`/api/v1/organizations/${organizationId}`, { method: 'DELETE' });
  }

  counterparties(): Promise<Counterparty[]> {
    return this.request<Counterparty[]>('/api/v1/counterparties');
  }

  createCounterparty(body: CounterpartyRequest): Promise<Counterparty> {
    return this.request<Counterparty>('/api/v1/counterparties', { method: 'POST', body });
  }

  updateCounterparty(counterpartyId: number, body: CounterpartyRequest): Promise<Counterparty> {
    return this.request<Counterparty>(`/api/v1/counterparties/${counterpartyId}`, {
      method: 'PUT',
      body,
    });
  }

  deleteCounterparty(counterpartyId: number): Promise<void> {
    return this.request<void>(`/api/v1/counterparties/${counterpartyId}`, { method: 'DELETE' });
  }

  recognizeRequisites(file: Blob): Promise<RecognizedRequisites> {
    return this.request<RecognizedRequisites>('/api/v1/requisites/recognize', {
      method: 'POST',
      file,
    });
  }
}
