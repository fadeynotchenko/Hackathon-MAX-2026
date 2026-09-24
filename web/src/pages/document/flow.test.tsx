// Сквозной путь по экранам документа: ошибка исправляется в той же форме,
// проверка пускает к экспорту только готовый документ, экспорт отправляет
// выбранный формат с текстом и ведёт на экран «отправлено».
import { fireEvent, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { makeDocument, mockApi, renderScreen } from '@/test-utils';

import { ExportPage } from './ExportPage';
import { FillPage } from './FillPage';
import { ReviewPage } from './ReviewPage';

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
    fireEvent.change(screen.getByLabelText(/ИНН клиента/), { target: { value: '123' } });
    fireEvent.click(screen.getByRole('button', { name: 'Проверить документ' }));

    expect(await screen.findByText('Исправьте 2 поля')).toBeInTheDocument();
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
    fireEvent.click(await screen.findByRole('button', { name: 'Выбрать формат файла' }));
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
