// Экран метрик: итоги периода, смена периода без мигания и ошибка с повтором.
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ApiError, type AdminMetrics } from '@/api/client';
import { mockApi, renderScreen } from '@/test-utils';

import { AdminPage } from './AdminPage';
import { makeMetrics } from './fixtures';

function setup(load: (days: number) => Promise<AdminMetrics>) {
  const api = mockApi();
  const adminMetrics = vi.spyOn(api, 'adminMetrics').mockImplementation(load);
  renderScreen(<AdminPage />, { api, path: '/admin', route: '/admin' });
  return adminMetrics;
}

describe('AdminPage', () => {
  it('opens on the last 30 days with totals, funnel, autofill and caught errors', async () => {
    const adminMetrics = setup(() => Promise.resolve(makeMetrics()));

    expect(await screen.findByText('Пользователей')).toBeInTheDocument();
    expect(adminMetrics).toHaveBeenCalledWith(30);
    expect(screen.getByText('24 сент. – 25 сент. 2026 г.')).toBeInTheDocument();
    expect(screen.getByText('42')).toBeInTheDocument();
    expect(screen.getByText('+4 за период')).toBeInTheDocument();
    expect(screen.getByText('1 на основе прошлых')).toBeInTheDocument();

    const funnel = screen.getByRole('list', { name: 'Воронка документов' });
    expect(
      within(funnel)
        .getAllByRole('listitem')
        // Intl ставит перед «%» неразрывный пробел.
        .map((row) => row.textContent?.replace(/\u00a0/g, ' ')),
    ).toEqual([
      'Создан5 · 100 %',
      'Все поля заполнены4 · 80 %',
      'Файл собран3 · 60 %',
      'Отправлен в чат2 · 40 %',
      'Доставлен в чат2 · 40 %',
    ]);
    const sources = screen.getByRole('list', { name: 'Поля документов по источнику' });
    expect(within(sources).getByText('Вручную')).toBeInTheDocument();
    expect(screen.getByText('ИНН не прошёл проверку')).toBeInTheDocument();
    expect(screen.getByText('Сборка PDF')).toBeInTheDocument();
    // Testing Library сводит неразрывный пробел к обычному.
    expect(screen.getByText('12 мин')).toBeInTheDocument();
  });

  it('keeps the previous period on screen while the next one loads', async () => {
    let finish: (value: AdminMetrics) => void = () => undefined;
    const adminMetrics = setup((days) =>
      days === 30
        ? Promise.resolve(makeMetrics())
        : new Promise((resolve) => {
            finish = resolve;
          }),
    );
    await screen.findByText('42');

    fireEvent.click(screen.getByRole('button', { name: 'Полгода' }));

    expect(adminMetrics).toHaveBeenLastCalledWith(180);
    expect(screen.getByRole('button', { name: 'Полгода' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText('42')).toBeInTheDocument();
    expect(document.querySelector('.dashboard')).toHaveAttribute('aria-busy', 'true');

    finish(makeMetrics({ since: '2026-03-30' }));
    await waitFor(() =>
      expect(document.querySelector('.dashboard')).toHaveAttribute('aria-busy', 'false'),
    );
    expect(screen.getByText('30 мар. – 25 сент. 2026 г.')).toBeInTheDocument();
  });

  it('explains a failed load and retries it', async () => {
    const adminMetrics = setup(() =>
      Promise.reject(new ApiError(403, 'auth.forbidden', 'Недостаточно прав', null)),
    );

    expect(await screen.findByText('Недостаточно прав')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Попробовать снова' }));

    await waitFor(() => expect(adminMetrics).toHaveBeenCalledTimes(2));
  });
});
