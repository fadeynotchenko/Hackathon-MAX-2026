// Экраны способов заполнения: запрос уходит с тем, что дал человек, удачный
// ответ возвращает в форму с плашкой, пустой — оставляет на экране с ответом
// помощника, а ответ после ухода «Назад» формы уже не касается. Запись голоса
// в jsdom — поддельный MediaRecorder; без него экран предлагает готовый файл.
import { MaxUI } from '@maxhub/max-ui';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { AgentFillResponse, ApiClient, FieldError } from '@/api/client';
import { AuthContext, type AuthState } from '@/auth/context';
import { makeDocument, mockApi, renderScreen } from '@/test-utils';

import { dropNotice, emptyNotice, filledNotice, peekNotice } from './fillMethods';
import { PhotoFillPage } from './PhotoFillPage';
import { TextFillPage } from './TextFillPage';
import { VoiceFillPage } from './VoiceFillPage';

function fillResult(overrides: Partial<AgentFillResponse> = {}): AgentFillResponse {
  return {
    reply: 'Заполнил: название клиента, сумма к оплате.',
    filled: ['client_name', 'total'],
    rejected: [],
    document: makeDocument(),
    ...overrides,
  };
}

const innError: FieldError = {
  key: 'client_inn',
  code: 'field.inn_invalid',
  message: '«ИНН клиента»: ИНН не проходит проверку',
};

function pickFile(container: HTMLElement, file: File) {
  const input = container.querySelector<HTMLInputElement>('input[type="file"]');
  if (!input) throw new Error('нет поля выбора файла');
  fireEvent.change(input, { target: { files: [file] } });
}

function Location() {
  return <span data-testid="location">{useLocation().pathname}</span>;
}

// Экран текста, открытый из формы, а форма — из каталога: «Назад» идёт по
// истории, и лишний шаг назад был бы виден по адресу.
function renderTextOverForm(api: ApiClient) {
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
        <MemoryRouter
          initialEntries={['/create/3', '/documents/7/fill', '/documents/7/fill/text']}
          initialIndex={2}
        >
          <Routes>
            <Route path="/documents/:documentId/fill/text" element={<TextFillPage />} />
            <Route path="*" element={<span>другой экран</span>} />
          </Routes>
          <Location />
        </MemoryRouter>
      </AuthContext.Provider>
    </MaxUI>,
  );
}

afterEach(() => {
  dropNotice(7);
});

describe('fill notices', () => {
  it('counts filled fields and names rejected values with their field', () => {
    expect(filledNotice(fillResult({ rejected: [innError] }))).toEqual({
      tone: 'success',
      title: 'Заполнено 2 поля — проверьте',
      text: 'Не записали: ИНН клиента — ИНН не проходит проверку.',
    });
    expect(filledNotice(fillResult({ filled: ['total'] }))).toEqual({
      tone: 'success',
      title: 'Заполнено 1 поле — проверьте',
    });
  });

  it('shows what was heard in a voice message', () => {
    const notice = emptyNotice({
      ...fillResult({ filled: [], reply: 'В сообщении не нашёл значений для полей документа.' }),
      transcript: 'Добрый день',
    });
    expect(notice).toEqual({
      tone: 'info',
      title: 'Ничего не заполнено',
      text: 'Помощник расслышал: «Добрый день». В сообщении не нашёл значений для полей документа.',
    });
  });
});

describe('text fill', () => {
  it('sends the message and returns to the form with a notice', async () => {
    const api = mockApi();
    const fill = vi.spyOn(api, 'fillFromMessage').mockResolvedValue(fillResult());
    renderScreen(<TextFillPage />, {
      api,
      path: '/documents/:documentId/fill/text',
      route: '/documents/7/fill/text',
    });

    const submit = screen.getByRole('button', { name: 'Заполнить' });
    expect(submit).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Данные для документа'), {
      target: { value: '  Для ООО «Альфа» на 180 000 ₽  ' },
    });
    fireEvent.click(submit);

    await waitFor(() =>
      expect(screen.getByTestId('location')).toHaveTextContent(/^\/documents\/7\/fill$/),
    );
    expect(fill).toHaveBeenCalledWith(7, 'Для ООО «Альфа» на 180 000 ₽');
    expect(peekNotice(7)).toMatchObject({ title: 'Заполнено 2 поля — проверьте' });
  });

  it('stays with the reply when nothing was filled', async () => {
    const api = mockApi();
    vi.spyOn(api, 'fillFromMessage').mockResolvedValue(
      fillResult({
        filled: [],
        reply: 'В сообщении не нашёл значений для полей документа. Ещё нужно: сумма к оплате.',
      }),
    );
    renderScreen(<TextFillPage />, {
      api,
      path: '/documents/:documentId/fill/text',
      route: '/documents/7/fill/text',
    });

    fireEvent.change(screen.getByLabelText('Данные для документа'), {
      target: { value: 'Привет' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Заполнить' }));

    expect(await screen.findByText('Ничего не заполнено')).toBeInTheDocument();
    expect(screen.getByText(/Ещё нужно: сумма к оплате/)).toBeInTheDocument();
    expect(screen.getByTestId('location')).toHaveTextContent('/documents/7/fill/text');
    expect(screen.getByLabelText('Данные для документа')).toHaveValue('Привет');
    expect(peekNotice(7)).toBeNull();
  });

  it('shows the server error and stays', async () => {
    const api = mockApi();
    vi.spyOn(api, 'fillFromMessage').mockRejectedValue(new Error('boom'));
    renderScreen(<TextFillPage />, {
      api,
      path: '/documents/:documentId/fill/text',
      route: '/documents/7/fill/text',
    });

    fireEvent.change(screen.getByLabelText('Данные для документа'), {
      target: { value: 'Счёт на 100 ₽' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Заполнить' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Не удалось заполнить поля');
    expect(screen.getByTestId('location')).toHaveTextContent('/documents/7/fill/text');
  });

  it('leaves the form alone when the answer comes after Back', async () => {
    const api = mockApi();
    let answer: (result: AgentFillResponse) => void = () => undefined;
    vi.spyOn(api, 'fillFromMessage').mockReturnValue(
      new Promise((resolve) => {
        answer = resolve;
      }),
    );
    renderTextOverForm(api);

    fireEvent.change(screen.getByLabelText('Данные для документа'), {
      target: { value: 'Счёт для Альфы на 180 000 ₽' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Заполнить' }));
    fireEvent.click(screen.getByRole('button', { name: 'Назад' }));
    expect(screen.getByTestId('location')).toHaveTextContent(/^\/documents\/7\/fill$/);

    await act(async () => {
      answer(fillResult());
      await Promise.resolve();
    });

    expect(screen.getByTestId('location')).toHaveTextContent(/^\/documents\/7\/fill$/);
    expect(peekNotice(7)).toBeNull();
  });
});

describe('photo fill', () => {
  it('recognizes the chosen file with the hint', async () => {
    const api = mockApi();
    const recognize = vi.spyOn(api, 'recognizeIntoDocument').mockResolvedValue(fillResult());
    const { container } = renderScreen(<PhotoFillPage />, {
      api,
      path: '/documents/:documentId/fill/photo',
      route: '/documents/7/fill/photo',
    });

    expect(screen.getByRole('button', { name: 'Заполнить' })).toBeDisabled();
    const photo = new File(['jpeg'], 'карточка.jpg', { type: 'image/jpeg' });
    pickFile(container, photo);
    expect(screen.getByText('карточка.jpg')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/Подсказка/), {
      target: { value: 'реквизиты покупателя' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Заполнить' }));

    await waitFor(() => expect(recognize).toHaveBeenCalledWith(7, photo, 'реквизиты покупателя'));
    await waitFor(() =>
      expect(screen.getByTestId('location')).toHaveTextContent(/^\/documents\/7\/fill$/),
    );
  });
});

describe('voice fill', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    Reflect.deleteProperty(navigator, 'mediaDevices');
  });

  it('offers an audio file where recording is unavailable', async () => {
    const api = mockApi();
    const voice = vi
      .spyOn(api, 'voiceIntoDocument')
      .mockResolvedValue({ ...fillResult(), transcript: 'Счёт для Альфы на 180 тысяч' });
    const { container } = renderScreen(<VoiceFillPage />, {
      api,
      path: '/documents/:documentId/fill/voice',
      route: '/documents/7/fill/voice',
    });

    expect(screen.getByText('Запись с микрофона здесь недоступна')).toBeInTheDocument();
    expect(container.querySelector('input[type="file"]')).toHaveAttribute('accept', 'audio/*');
    const audio = new File(['OggS'], 'голосовое.ogg', { type: 'audio/ogg' });
    pickFile(container, audio);
    fireEvent.click(screen.getByRole('button', { name: 'Заполнить' }));

    await waitFor(() => expect(voice).toHaveBeenCalledWith(7, audio));
    await waitFor(() =>
      expect(screen.getByTestId('location')).toHaveTextContent(/^\/documents\/7\/fill$/),
    );
    expect(peekNotice(7)?.text).toBe('Помощник расслышал: «Счёт для Альфы на 180 тысяч».');
  });

  it('falls back to a file when the microphone is denied', async () => {
    vi.stubGlobal('MediaRecorder', FakeRecorder);
    stubMicrophone(vi.fn().mockRejectedValue(new DOMException('denied', 'NotAllowedError')));
    renderScreen(<VoiceFillPage />, {
      api: mockApi(),
      path: '/documents/:documentId/fill/voice',
      route: '/documents/7/fill/voice',
    });

    fireEvent.click(screen.getByRole('button', { name: 'Начать запись' }));

    expect(await screen.findByText('Нет доступа к микрофону')).toBeInTheDocument();
    expect(screen.getByText('Выбрать аудиофайл')).toBeInTheDocument();
  });

  it('records, stops the microphone and sends the recording', async () => {
    vi.stubGlobal('MediaRecorder', FakeRecorder);
    const track = { stop: vi.fn() };
    const getUserMedia = vi.fn().mockResolvedValue({ getTracks: () => [track] });
    stubMicrophone(getUserMedia);
    const api = mockApi();
    const voice = vi
      .spyOn(api, 'voiceIntoDocument')
      .mockResolvedValue({ ...fillResult(), transcript: 'Счёт для Альфы' });
    renderScreen(<VoiceFillPage />, {
      api,
      path: '/documents/:documentId/fill/voice',
      route: '/documents/7/fill/voice',
    });

    expect(screen.getByRole('button', { name: 'Заполнить' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Начать запись' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Остановить запись' }));

    expect(await screen.findByRole('button', { name: 'Записать заново' })).toBeInTheDocument();
    expect(getUserMedia).toHaveBeenCalledWith({ audio: true });
    expect(track.stop).toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Заполнить' }));

    await waitFor(() => expect(voice).toHaveBeenCalledTimes(1));
    const sent = voice.mock.calls[0]![1];
    expect(sent.type).toBe('audio/webm;codecs=opus');
    expect(sent.size).toBeGreaterThan(0);
  });

  it('drops the old recording when recording again fails', async () => {
    vi.stubGlobal('MediaRecorder', FakeRecorder);
    const getUserMedia = vi
      .fn()
      .mockResolvedValueOnce({ getTracks: () => [{ stop: vi.fn() }] })
      .mockRejectedValueOnce(new DOMException('busy', 'NotReadableError'));
    stubMicrophone(getUserMedia);
    const api = mockApi();
    const voice = vi.spyOn(api, 'voiceIntoDocument');
    renderScreen(<VoiceFillPage />, {
      api,
      path: '/documents/:documentId/fill/voice',
      route: '/documents/7/fill/voice',
    });

    fireEvent.click(screen.getByRole('button', { name: 'Начать запись' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Остановить запись' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Записать заново' }));

    expect(await screen.findByText('Не удалось включить микрофон')).toBeInTheDocument();
    expect(screen.getByText('Выбрать аудиофайл')).toBeInTheDocument();
    const submit = screen.getByRole('button', { name: 'Заполнить' });
    expect(submit).toBeDisabled();
    fireEvent.click(submit);
    expect(voice).not.toHaveBeenCalled();
  });

  it('turns the microphone off when the screen closes mid-recording', async () => {
    vi.stubGlobal('MediaRecorder', FakeRecorder);
    const track = { stop: vi.fn() };
    stubMicrophone(vi.fn().mockResolvedValue({ getTracks: () => [track] }));
    const { unmount } = renderScreen(<VoiceFillPage />, {
      api: mockApi(),
      path: '/documents/:documentId/fill/voice',
      route: '/documents/7/fill/voice',
    });

    fireEvent.click(screen.getByRole('button', { name: 'Начать запись' }));
    await screen.findByRole('button', { name: 'Остановить запись' });
    unmount();

    expect(track.stop).toHaveBeenCalled();
  });
});

// Поддельный MediaRecorder: отдаёт один кусок при остановке, как настоящий
// без timeslice. Формат — второй из списка экрана, чтобы проверить выбор.
class FakeRecorder {
  static isTypeSupported(type: string): boolean {
    return type === 'audio/webm;codecs=opus';
  }

  state: 'inactive' | 'recording' = 'inactive';
  readonly mimeType: string;
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;

  constructor(_stream: unknown, options?: { mimeType?: string }) {
    this.mimeType = options?.mimeType ?? '';
  }

  start(): void {
    this.state = 'recording';
  }

  stop(): void {
    this.state = 'inactive';
    this.ondataavailable?.({ data: new Blob(['voice'], { type: this.mimeType }) });
    this.onstop?.();
  }
}

function stubMicrophone(getUserMedia: ReturnType<typeof vi.fn>) {
  Object.defineProperty(navigator, 'mediaDevices', {
    configurable: true,
    value: { getUserMedia },
  });
}
