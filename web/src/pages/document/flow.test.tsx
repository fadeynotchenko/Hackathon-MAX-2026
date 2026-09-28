// Сквозной путь по экранам документа: ошибка исправляется в той же форме,
// способ заполнения (фото, голос, текст) открывается после сохранения правок и
// возвращает в форму с плашкой, проверка пускает к экспорту только готовый
// документ, экспорт отправляет выбранный формат с текстом и ведёт на экран
// «отправлено». Кнопка тестовых данных есть только у администратора. Действия
// формы идут по одному, «Назад» во время сохранения никуда потом не уводит, а
// отклонённая правка не теряется ни при повторном тапе, ни при правке соседнего поля.
import { act, fireEvent, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { ApiClient, DocumentView } from '@/api/client';
import { makeDocument, mockApi, renderScreen } from '@/test-utils';

import { ExportPage } from './ExportPage';
import { FillPage } from './FillPage';
import { ReviewPage } from './ReviewPage';
import { TextFillPage } from './TextFillPage';

// Форма и экран текста в одном роутере — чтобы пройти туда и обратно по
// истории; пользователь — обычный или администратор.
function renderForm(api: ApiClient, { admin = false }: { admin?: boolean } = {}) {
  return renderScreen(<FillPage />, {
    api,
    path: '/documents/:documentId/fill',
    route: '/documents/7/fill',
    user: { is_admin: admin },
    routes: [{ path: '/documents/:documentId/fill/text', element: <TextFillPage /> }],
  });
}

const innRejected = {
  key: 'client_inn',
  code: 'field.inn_invalid',
  message: '«ИНН клиента»: ИНН не проходит проверку',
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

const ready = makeDocument({
  status: 'ready',
  ready: true,
  missing: [],
  values: {
    client_name: {
      value: 'ООО «Альфа»',
      source: 'manual',
      confirmed: true,
      fragment: null,
      confidence: null,
    },
    total: {
      value: '180000.00',
      source: 'manual',
      confirmed: true,
      fragment: null,
      confidence: null,
    },
    seller_name: {
      value: 'ООО «Мастер»',
      source: 'profile',
      confirmed: true,
      fragment: null,
      confidence: null,
    },
  },
});

describe('document flow', () => {
  it('keeps the person on the form until errors are fixed', async () => {
    const api = mockApi();
    vi.spyOn(api, 'document').mockResolvedValue(makeDocument());
    const setFields = vi
      .spyOn(api, 'setFields')
      .mockResolvedValueOnce(
        makeDocument({
          missing: ['total'],
          errors: [
            {
              key: 'client_inn',
              code: 'field.inn_invalid',
              message: '«ИНН клиента»: ИНН не проходит проверку',
            },
          ],
          values: {
            client_name: {
              value: 'ООО «Альфа»',
              source: 'manual',
              confirmed: true,
              fragment: null,
              confidence: null,
            },
            seller_name: {
              value: 'ООО «Мастер»',
              source: 'profile',
              confirmed: true,
              fragment: null,
              confidence: null,
            },
          },
        }),
      )
      .mockResolvedValueOnce(ready);

    renderScreen(<FillPage />, {
      api,
      path: '/documents/:documentId/fill',
      route: '/documents/7/fill',
    });

    fireEvent.change(await screen.findByLabelText(/Название клиента/), {
      target: { value: 'ООО «Альфа»' },
    });
    // Пустое необязательное поле свёрнуто, пока его не попросили.
    expect(screen.queryByLabelText(/ИНН клиента/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Ещё 1 поле' }));
    fireEvent.change(screen.getByLabelText(/ИНН клиента/), { target: { value: '123' } });
    fireEvent.click(screen.getByRole('button', { name: 'Проверить документ' }));

    // Ошибка держит на форме, пустое поле — только подсвечено.
    expect(await screen.findByText('Исправьте 1 поле')).toBeInTheDocument();
    expect(screen.getByText('ИНН не проходит проверку')).toBeInTheDocument();
    expect(screen.getByText('Заполните поле')).toBeInTheDocument();
    // Реквизиты продавца из профиля не уходят повторно и не становятся «вручную».
    expect(setFields).toHaveBeenLastCalledWith(7, {
      client_name: 'ООО «Альфа»',
      client_inn: '123',
    });
    expect(screen.getByLabelText(/ИНН клиента/)).toHaveValue('123');

    fireEvent.change(screen.getByLabelText(/ИНН клиента/), { target: { value: '' } });
    fireEvent.change(screen.getByLabelText(/Сумма к оплате/), { target: { value: '180 000' } });
    fireEvent.click(screen.getByRole('button', { name: 'Проверить документ' }));

    await waitFor(() =>
      expect(screen.getByTestId('location')).toHaveTextContent('/documents/7/review'),
    );
    expect(setFields).toHaveBeenLastCalledWith(7, { client_inn: '', total: '180 000' });
  });

  it('asks before leaving required fields empty and lets them stay empty', async () => {
    const api = mockApi();
    vi.spyOn(api, 'document').mockResolvedValue(makeDocument());
    vi.spyOn(api, 'setFields').mockResolvedValue(makeDocument());
    renderForm(api);

    fireEvent.change(await screen.findByLabelText(/Название клиента/), {
      target: { value: '' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Проверить документ' }));
    expect(await screen.findByRole('alertdialog')).toHaveTextContent('Оставить пустыми 2 поля?');

    fireEvent.click(screen.getByRole('button', { name: 'Заполнить' }));
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(screen.getByTestId('location')).toHaveTextContent('/documents/7/fill');

    fireEvent.click(screen.getByRole('button', { name: 'Проверить документ' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Да, оставить пустыми' }));
    await waitFor(() =>
      expect(screen.getByTestId('location')).toHaveTextContent('/documents/7/review'),
    );
  });

  it('does not label a rejected value with the source of the kept one', async () => {
    const fromCard = {
      value: '7736207543',
      source: 'counterparty' as const,
      confirmed: true,
      fragment: null,
      confidence: null,
    };
    const api = mockApi();
    vi.spyOn(api, 'document').mockResolvedValue(makeDocument({ values: { client_inn: fromCard } }));
    vi.spyOn(api, 'setFields').mockResolvedValueOnce(
      makeDocument({
        // Сервер отклонил правку и оставил прежний ИНН из карточки.
        values: { client_inn: fromCard },
        errors: [
          {
            key: 'client_inn',
            code: 'field.inn_invalid',
            message: '«ИНН клиента»: ИНН не проходит проверку',
          },
        ],
      }),
    );
    renderScreen(<FillPage />, {
      api,
      path: '/documents/:documentId/fill',
      route: '/documents/7/fill',
    });
    expect(await screen.findByText('Из карточки')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/ИНН клиента/), { target: { value: '7707083894' } });
    fireEvent.click(screen.getByRole('button', { name: 'Проверить документ' }));

    expect(await screen.findByText('ИНН не проходит проверку')).toBeInTheDocument();
    expect(screen.getByLabelText(/ИНН клиента/)).toHaveValue('7707083894');
    expect(screen.queryByText('Из карточки')).not.toBeInTheDocument();
  });

  it('offers photo, voice and text filling at the top of the form', async () => {
    const api = mockApi();
    vi.spyOn(api, 'document').mockResolvedValue(makeDocument());
    renderForm(api);

    for (const name of ['С фото', 'Голосом', 'Текстом']) {
      expect(await screen.findByRole('button', { name })).toBeEnabled();
    }
    expect(
      screen.queryByRole('button', { name: 'Заполнить демо-данными' }),
    ).not.toBeInTheDocument();
  });

  it('saves unsaved edits before opening a fill method', async () => {
    const api = mockApi();
    vi.spyOn(api, 'document').mockResolvedValue(makeDocument());
    const setFields = vi.spyOn(api, 'setFields').mockResolvedValue(
      makeDocument({
        values: {
          ...makeDocument().values,
          client_name: {
            value: 'ООО «Альфа»',
            source: 'manual',
            confirmed: true,
            fragment: null,
            confidence: null,
          },
        },
      }),
    );
    renderForm(api);

    fireEvent.change(await screen.findByLabelText(/Название клиента/), {
      target: { value: 'ООО «Альфа»' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Текстом' }));

    await waitFor(() =>
      expect(screen.getByTestId('location')).toHaveTextContent('/documents/7/fill/text'),
    );
    expect(setFields).toHaveBeenCalledWith(7, { client_name: 'ООО «Альфа»' });
  });

  it('stays on the form when the edits could not be saved', async () => {
    const api = mockApi();
    vi.spyOn(api, 'document').mockResolvedValue(makeDocument());
    vi.spyOn(api, 'setFields').mockRejectedValue(new Error('offline'));
    renderForm(api);

    fireEvent.change(await screen.findByLabelText(/Название клиента/), {
      target: { value: 'ООО «Альфа»' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'С фото' }));

    expect(await screen.findByText('Не удалось сохранить')).toBeInTheDocument();
    expect(screen.getByTestId('location')).toHaveTextContent(/^\/documents\/7\/fill$/);
    expect(screen.getByLabelText(/Название клиента/)).toHaveValue('ООО «Альфа»');
  });

  it('comes back from text filling with the values and a notice', async () => {
    const api = mockApi();
    const filled = makeDocument({
      values: {
        ...makeDocument().values,
        client_name: {
          value: 'ООО «Альфа»',
          source: 'agent',
          confirmed: false,
          fragment: 'ООО «Альфа»',
          confidence: null,
        },
        total: {
          value: '180000.00',
          source: 'agent',
          confirmed: false,
          fragment: '180 тысяч',
          confidence: null,
        },
      },
      missing: [],
      unconfirmed: ['client_name', 'total'],
    });
    const load = vi
      .spyOn(api, 'document')
      .mockResolvedValueOnce(makeDocument())
      .mockResolvedValue(filled);
    vi.spyOn(api, 'fillFromMessage').mockResolvedValue({
      reply: 'Заполнил: название клиента, сумма к оплате.',
      filled: ['client_name', 'total'],
      rejected: [
        {
          key: 'client_inn',
          code: 'field.inn_invalid',
          message: '«ИНН клиента»: ИНН не проходит проверку',
        },
      ],
      document: filled,
    });
    renderForm(api);

    fireEvent.click(await screen.findByRole('button', { name: 'Текстом' }));
    fireEvent.change(await screen.findByLabelText('Данные для документа'), {
      target: { value: 'Для ООО «Альфа», ИНН 123, на 180 тысяч' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Заполнить' }));

    expect(await screen.findByText('Заполнено 2 поля — проверьте')).toBeInTheDocument();
    expect(
      screen.getByText('Не записали: ИНН клиента — ИНН не проходит проверку.'),
    ).toBeInTheDocument();
    expect(screen.getByTestId('location')).toHaveTextContent(/^\/documents\/7\/fill$/);
    expect(screen.getByLabelText(/Название клиента/)).toHaveValue('ООО «Альфа»');
    expect(screen.getByLabelText(/Сумма к оплате/)).toHaveValue('180 000');
    expect(load).toHaveBeenCalledTimes(2);
  });

  it('lets an admin fill every field with test data', async () => {
    const api = mockApi();
    const doc = makeDocument();
    vi.spyOn(api, 'document').mockResolvedValue(doc);
    const setFields = vi.spyOn(api, 'setFields').mockImplementation(async (_id, values) =>
      makeDocument({
        values: Object.fromEntries(
          Object.entries(values).map(([key, value]) => [
            key,
            { value, source: 'manual', confirmed: true, fragment: null, confidence: null },
          ]),
        ),
        missing: [],
      }),
    );
    renderForm(api, { admin: true });

    fireEvent.click(await screen.findByRole('button', { name: 'Заполнить демо-данными' }));

    expect(await screen.findByText('Демо-данные подставлены')).toBeInTheDocument();
    const sent = setFields.mock.calls[0]![1];
    expect(Object.keys(sent).sort()).toEqual(doc.template.fields.map((f) => f.key).sort());
    for (const value of Object.values(sent)) expect(value.trim()).not.toBe('');
    // Свёрнутое необязательное поле и реквизиты продавца раскрыты.
    expect(screen.getByLabelText(/ИНН клиента/)).toHaveValue(sent['client_inn']);
    expect(screen.getByLabelText(/Название продавца/)).toBeInTheDocument();
  });

  it('runs one form action at a time', async () => {
    const api = mockApi();
    vi.spyOn(api, 'document').mockResolvedValue(makeDocument());
    const setFields = vi.spyOn(api, 'setFields').mockReturnValue(new Promise(() => {}));
    renderForm(api, { admin: true });

    fireEvent.change(await screen.findByLabelText(/Название клиента/), {
      target: { value: 'ООО «Альфа»' },
    });
    // Второй тап приходит раньше перерисовки с выключенными кнопками.
    act(() => {
      fireEvent.click(screen.getByRole('button', { name: 'Текстом' }));
      fireEvent.click(screen.getByRole('button', { name: 'Проверить документ' }));
      fireEvent.click(screen.getByRole('button', { name: 'Заполнить демо-данными' }));
    });

    expect(setFields).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button', { name: 'Проверить документ' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'С фото' })).toBeDisabled();
  });

  it('keeps the check off while test data is being applied', async () => {
    const api = mockApi();
    vi.spyOn(api, 'document').mockResolvedValue(makeDocument());
    vi.spyOn(api, 'setFields').mockReturnValue(new Promise(() => {}));
    renderForm(api, { admin: true });

    fireEvent.click(await screen.findByRole('button', { name: 'Заполнить демо-данными' }));

    expect(screen.getByRole('button', { name: 'Проверить документ' })).toBeDisabled();
  });

  it('does not open a fill method after the person went back', async () => {
    const api = mockApi();
    vi.spyOn(api, 'document').mockResolvedValue(makeDocument());
    const saved = deferred<DocumentView>();
    vi.spyOn(api, 'setFields').mockReturnValue(saved.promise);
    renderForm(api);

    fireEvent.change(await screen.findByLabelText(/Название клиента/), {
      target: { value: 'ООО «Альфа»' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Текстом' }));
    fireEvent.click(screen.getByRole('button', { name: 'Назад' }));
    expect(screen.getByTestId('location')).toHaveTextContent(/^\/documents\/7$/);

    await act(async () => saved.resolve(makeDocument()));

    expect(screen.getByTestId('location')).toHaveTextContent(/^\/documents\/7$/);
  });

  it('stays on the form on a second tap after a rejected edit', async () => {
    const api = mockApi();
    vi.spyOn(api, 'document').mockResolvedValue(makeDocument());
    // Сервер отклоняет ИНН и хранит прежнее (пустое) значение.
    const setFields = vi
      .spyOn(api, 'setFields')
      .mockResolvedValue(makeDocument({ errors: [innRejected] }));
    renderForm(api);

    fireEvent.click(await screen.findByRole('button', { name: 'Ещё 1 поле' }));
    fireEvent.change(screen.getByLabelText(/ИНН клиента/), { target: { value: '123' } });
    fireEvent.click(screen.getByRole('button', { name: 'Текстом' }));
    expect(await screen.findByText('Исправьте 1 поле')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Текстом' }));

    await waitFor(() => expect(setFields).toHaveBeenCalledTimes(2));
    expect(setFields).toHaveBeenLastCalledWith(7, { client_inn: '123' });
    expect(await screen.findByText('Исправьте 1 поле')).toBeInTheDocument();
    expect(screen.getByTestId('location')).toHaveTextContent(/^\/documents\/7\/fill$/);
    expect(screen.getByLabelText(/ИНН клиента/)).toHaveValue('123');
  });

  it('keeps a rejected edit when another field is saved', async () => {
    const api = mockApi();
    vi.spyOn(api, 'document').mockResolvedValue(makeDocument());
    const setFields = vi
      .spyOn(api, 'setFields')
      .mockResolvedValueOnce(makeDocument({ errors: [innRejected] }))
      .mockResolvedValueOnce(
        makeDocument({
          errors: [innRejected],
          values: {
            ...makeDocument().values,
            client_name: {
              value: 'ООО «Альфа»',
              source: 'manual',
              confirmed: true,
              fragment: null,
              confidence: null,
            },
          },
        }),
      );
    renderForm(api);

    fireEvent.click(await screen.findByRole('button', { name: 'Ещё 1 поле' }));
    fireEvent.change(screen.getByLabelText(/ИНН клиента/), { target: { value: '123' } });
    fireEvent.click(screen.getByRole('button', { name: 'Проверить документ' }));
    expect(await screen.findByText('ИНН не проходит проверку')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/Название клиента/), {
      target: { value: 'ООО «Альфа»' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Проверить документ' }));

    await waitFor(() => expect(setFields).toHaveBeenCalledTimes(2));
    expect(setFields).toHaveBeenLastCalledWith(7, {
      client_inn: '123',
      client_name: 'ООО «Альфа»',
    });
    expect(await screen.findByText('ИНН не проходит проверку')).toBeInTheDocument();
    expect(screen.getByLabelText(/ИНН клиента/)).toHaveValue('123');
  });

  it('asks to confirm recognized values before export', async () => {
    const api = mockApi();
    const pending = makeDocument({
      ...ready,
      ready: false,
      unconfirmed: ['total'],
      values: {
        ...ready.values,
        total: {
          value: '180000.00',
          source: 'ocr',
          confirmed: false,
          fragment: 'Итого: 180 000,00',
          confidence: 0.9,
        },
      },
    });
    vi.spyOn(api, 'document').mockResolvedValue(pending);
    const confirm = vi.spyOn(api, 'confirmFields').mockResolvedValue(ready);

    renderScreen(<ReviewPage />, {
      api,
      path: '/documents/:documentId/review',
      route: '/documents/7/review',
    });

    expect(await screen.findByText('На фото: «Итого: 180 000,00»')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Всё верно' }));
    await waitFor(() => expect(confirm).toHaveBeenCalledWith(7));
    fireEvent.click(await screen.findByRole('button', { name: 'Далее' }));
    expect(screen.getByTestId('location')).toHaveTextContent('/documents/7/export');
  });

  it('sends the chosen format with the cover text', async () => {
    const api = mockApi();
    vi.spyOn(api, 'document').mockResolvedValue(ready);
    const send = vi
      .spyOn(api, 'sendDocument')
      .mockResolvedValue({ event_id: 'e1', filename: 'Счёт.docx', format: 'docx' });

    renderScreen(<ExportPage />, {
      api,
      path: '/documents/:documentId/export',
      route: '/documents/7/export',
    });

    fireEvent.click(await screen.findByText('DOCX'));
    fireEvent.change(screen.getByLabelText('Сопроводительный текст'), {
      target: { value: 'Добрый день! Счёт во вложении.' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Отправить в чат' }));

    await waitFor(() =>
      expect(send).toHaveBeenCalledWith(7, 'docx', 'Добрый день! Счёт во вложении.'),
    );
    await waitFor(() =>
      expect(screen.getByTestId('location')).toHaveTextContent('/documents/7/sent'),
    );
  });
});
