// Свой шаблон с экрана: текст с полями, каталог реквизитов, тип поля и
// сохранение — новый шаблон ведёт на его карточку, правка уходит PUT.
import { fireEvent, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { makeTemplate, mockApi, renderScreen } from '@/test-utils';

import { TemplateEditorPage } from './TemplateEditorPage';

describe('TemplateEditorPage', () => {
  it('saves a new template with own and catalog fields', async () => {
    const api = mockApi();
    const create = vi
      .spyOn(api, 'createTemplate')
      .mockResolvedValue(makeTemplate({ id: 42, is_builtin: false }));
    renderScreen(<TemplateEditorPage />, { api, path: '/templates/new', route: '/templates/new' });

    fireEvent.change(screen.getByLabelText('Название шаблона'), {
      target: { value: 'Акт выполненных работ' },
    });
    const text = screen.getByLabelText('Текст документа');
    fireEvent.change(text, { target: { value: 'Акт для \nСрок: {{Срок поставки}}' } });
    (text as HTMLTextAreaElement).setSelectionRange(8, 8);
    fireEvent.select(text);
    fireEvent.click(screen.getByRole('button', { name: 'Вставить поле' }));
    const client = screen.getByRole('group', { name: 'Клиент' });
    fireEvent.click(
      Array.from(client.querySelectorAll('button')).find((b) => b.textContent === 'Название')!,
    );
    fireEvent.click(
      Array.from(
        screen.getByRole('group', { name: 'Тип поля «Срок поставки»' }).querySelectorAll('button'),
      ).find((b) => b.textContent === 'Дата')!,
    );

    expect(screen.getByText('Название клиента')).toBeInTheDocument();
    expect(screen.getByText(/подставится из карточки клиента/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить шаблон' }));

    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/create/42'));
    expect(create).toHaveBeenCalledWith({
      title: 'Акт выполненных работ',
      description: '',
      body: 'Акт для {{client_name}}\nСрок: {{srok_postavki}}',
      fields: [
        expect.objectContaining({ key: 'client_name', type: 'text', required: true }),
        expect.objectContaining({ key: 'srok_postavki', type: 'date', required: true }),
      ],
    });
  });

  it('does not send a template without fields', () => {
    const api = mockApi();
    const create = vi.spyOn(api, 'createTemplate');
    renderScreen(<TemplateEditorPage />, { api, path: '/templates/new', route: '/templates/new' });

    fireEvent.change(screen.getByLabelText('Название шаблона'), { target: { value: 'Письмо' } });
    fireEvent.change(screen.getByLabelText('Текст документа'), {
      target: { value: 'Просто текст' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить шаблон' }));

    expect(screen.getByText('Вставьте в текст хотя бы одно поле')).toBeInTheDocument();
    expect(create).not.toHaveBeenCalled();
  });

  it('edits an own template in place', async () => {
    const api = mockApi();
    const own = makeTemplate({
      id: 5,
      is_builtin: false,
      title: 'Мой счёт',
      body: 'Счёт для {{client_name}}',
      fields: [makeTemplate().fields[0]!],
    });
    vi.spyOn(api, 'template').mockResolvedValue(own);
    const update = vi.spyOn(api, 'updateTemplate').mockResolvedValue(own);
    renderScreen(<TemplateEditorPage />, {
      api,
      path: '/templates/:templateId/edit',
      route: '/templates/5/edit',
    });

    const text = await screen.findByLabelText('Текст документа');
    expect(text).toHaveValue('Счёт для {{Название клиента}}');
    fireEvent.change(text, { target: { value: 'Счёт № 1 для {{Название клиента}}' } });
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить шаблон' }));

    await waitFor(() =>
      expect(update).toHaveBeenCalledWith(
        5,
        expect.objectContaining({ title: 'Мой счёт', body: 'Счёт № 1 для {{client_name}}' }),
      ),
    );
  });
});
