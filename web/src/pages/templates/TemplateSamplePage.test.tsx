// Шаблон из файла с экрана: файл разобран, человек убирает лишнее место,
// отмечает пропущенное и сохраняет — шаблон уходит с образцом и местами.
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { TemplateImport } from '@/api/client';
import { makeTemplate, mockApi, renderScreen } from '@/test-utils';

import { TemplateSamplePage } from './TemplateSamplePage';

const imported: TemplateImport = {
  file_id: 9,
  filename: 'Фирменный_КП.docx',
  format: 'docx',
  title: 'Коммерческое предложение',
  text: 'Для: ООО «Альфа»\nСтоимость: 180 000 руб.\nОплата в течение 14 дней',
  found_by: 'assistant',
  notice: null,
  fields: [
    {
      key: 'client_name',
      label: 'Клиент',
      type: 'text',
      required: true,
      places: [{ text: 'ООО «Альфа»', before: '' }],
    },
    {
      key: '',
      label: 'Срок оплаты',
      type: 'integer',
      required: true,
      places: [{ text: '14', before: '' }],
    },
  ],
};

describe('TemplateSamplePage', () => {
  it('turns a sample file into a template the person checked', async () => {
    const api = mockApi();
    const importTemplate = vi.spyOn(api, 'importTemplate').mockResolvedValue(imported);
    const create = vi
      .spyOn(api, 'createTemplate')
      .mockResolvedValue(makeTemplate({ id: 42, is_builtin: false }));
    const { container } = renderScreen(<TemplateSamplePage />, {
      api,
      path: '/templates/upload',
      route: '/templates/upload',
    });

    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(['docx'], 'Фирменный_КП.docx');
    fireEvent.change(input, { target: { files: [file] } });

    expect(await screen.findByText('Помощник отметил 2 места для данных')).toBeInTheDocument();
    expect(importTemplate).toHaveBeenCalledWith(file);
    expect(screen.getByLabelText('Название шаблона')).toHaveValue('Коммерческое предложение');

    fireEvent.click(screen.getByRole('button', { name: 'Убрать поле «Срок оплаты»' }));
    fireEvent.change(screen.getByLabelText('Текст из файла'), { target: { value: '180 000' } });
    fireEvent.click(
      within(screen.getByRole('group', { name: 'Документ' })).getByRole('button', {
        name: 'Вставить «Сумма»',
      }),
    );
    expect(screen.getByText('В файле: «180 000»')).toBeInTheDocument();
    expect(screen.getByRole('document')).toHaveTextContent('Стоимость: {{Сумма}} руб.');

    fireEvent.click(screen.getByRole('button', { name: 'Сохранить шаблон' }));
    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('/create/42'));
    expect(create).toHaveBeenCalledWith({
      title: 'Коммерческое предложение',
      description: '',
      body: '',
      file_id: 9,
      fields: [
        expect.objectContaining({
          key: 'client_name',
          places: [{ text: 'ООО «Альфа»', before: '' }],
        }),
        expect.objectContaining({
          key: 'total',
          type: 'money',
          places: [{ text: '180 000', before: '' }],
        }),
      ],
    });
  });

  it('does not offer a place that is not in the file', async () => {
    const api = mockApi();
    vi.spyOn(api, 'importTemplate').mockResolvedValue({ ...imported, fields: [] });
    const { container } = renderScreen(<TemplateSamplePage />, {
      api,
      path: '/templates/upload',
      route: '/templates/upload',
    });
    fireEvent.change(container.querySelector('input[type="file"]')!, {
      target: { files: [new File(['x'], 'a.docx')] },
    });

    expect(await screen.findByText('Мест для данных не нашлось')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Текст из файла'), { target: { value: 'ООО «Гамма»' } });
    expect(screen.getByText(/Такого текста в файле нет/)).toBeInTheDocument();
    expect(screen.queryByRole('group', { name: 'Документ' })).not.toBeInTheDocument();
  });
});
