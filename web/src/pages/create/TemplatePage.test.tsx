// Экран шаблона: «Заполнить» сразу создаёт черновик и открывает форму, без
// выбора сторон и без напоминания про реквизиты; действия — по виду шаблона.
import { fireEvent, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ApiError, type Template } from '@/api/client';
import { makeDocument, makeTemplate, mockApi, renderScreen } from '@/test-utils';

import { TemplatePage } from './TemplatePage';

function setup(template: Template = makeTemplate({ id: 1 })) {
  const api = mockApi();
  vi.spyOn(api, 'template').mockResolvedValue(template);
  const organizations = vi.spyOn(api, 'organizations').mockResolvedValue([]);
  const createDocument = vi.spyOn(api, 'createDocument').mockResolvedValue(makeDocument({ id: 9 }));
  renderScreen(<TemplatePage />, { api, path: '/create/:templateId', route: '/create/1' });
  return { createDocument, organizations };
}

describe('TemplatePage', () => {
  it('creates the draft right away and opens the form', async () => {
    const { createDocument } = setup();

    fireEvent.click(await screen.findByRole('button', { name: 'Заполнить' }));

    await waitFor(() =>
      expect(screen.getByTestId('location')).toHaveTextContent('/documents/9/fill'),
    );
    expect(createDocument).toHaveBeenCalledWith({ template_id: 1 });
  });

  it('creates one draft on a double tap', async () => {
    const { createDocument } = setup();
    createDocument.mockReturnValue(new Promise(() => {}));
    const fill = await screen.findByRole('button', { name: 'Заполнить' });

    fireEvent.click(fill);
    fireEvent.click(fill);

    expect(createDocument).toHaveBeenCalledTimes(1);
  });

  it('says why the draft was not created and lets retry', async () => {
    const { createDocument } = setup();
    createDocument.mockRejectedValueOnce(
      new ApiError(404, 'template.not_found', 'Шаблон не найден', null),
    );

    fireEvent.click(await screen.findByRole('button', { name: 'Заполнить' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Шаблон не найден');
    fireEvent.click(screen.getByRole('button', { name: 'Заполнить' }));
    await waitFor(() =>
      expect(screen.getByTestId('location')).toHaveTextContent('/documents/9/fill'),
    );
    expect(createDocument).toHaveBeenCalledTimes(2);
  });

  it('does not nag about requisites', async () => {
    const { organizations } = setup();

    expect(await screen.findByRole('button', { name: 'Заполнить' })).toBeInTheDocument();
    expect(screen.queryByText('Добавьте свои реквизиты')).toBeNull();
    expect(organizations).not.toHaveBeenCalled();
  });

  it('offers to make an own template from a standard one', async () => {
    setup();

    fireEvent.click(await screen.findByText('Создать свой шаблон на основе этого'));

    expect(screen.getByText('другой экран')).toBeInTheDocument();
    expect(screen.getByTestId('location')).toHaveTextContent('/templates/new');
    expect(screen.queryByText('Изменить шаблон')).toBeNull();
  });

  it('lets edit or delete an own template', async () => {
    setup(makeTemplate({ id: 1, is_builtin: false }));

    expect(await screen.findByText('Изменить шаблон')).toBeInTheDocument();
    expect(screen.getByText('Удалить шаблон')).toBeInTheDocument();
    expect(screen.queryByText('Создать свой шаблон на основе этого')).toBeNull();
  });
});
