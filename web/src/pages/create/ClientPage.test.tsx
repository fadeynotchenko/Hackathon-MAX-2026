// Выбор сторон перед созданием: своя организация (если их несколько) и клиент.
import { fireEvent, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { Counterparty, Organization } from '@/api/client';
import { makeDocument, mockApi, renderScreen } from '@/test-utils';

import { ClientPage } from './ClientPage';

function organization(id: number, name: string, isDefault: boolean): Organization {
  return {
    id,
    name,
    inn: null,
    values: {},
    is_default: isDefault,
    created_at: '2026-09-24T10:00:00Z',
    updated_at: '2026-09-24T10:00:00Z',
  };
}

function client(id: number, name: string, inn: string): Counterparty {
  return {
    id,
    name,
    inn,
    values: {},
    created_at: '2026-09-24T10:00:00Z',
    updated_at: '2026-09-24T10:00:00Z',
  };
}

function setup(organizations: Organization[], counterparties: Counterparty[] = []) {
  const api = mockApi();
  vi.spyOn(api, 'counterparties').mockResolvedValue(counterparties);
  vi.spyOn(api, 'organizations').mockResolvedValue(organizations);
  const createDocument = vi.spyOn(api, 'createDocument').mockResolvedValue(makeDocument({ id: 9 }));
  renderScreen(<ClientPage />, {
    api,
    path: '/create/:templateId/client',
    route: '/create/1/client',
  });
  return createDocument;
}

describe('ClientPage', () => {
  it('filters clients by name or INN and says when nothing matches', async () => {
    setup(
      [organization(1, 'ООО «Ромашка»', true)],
      [client(1, 'ООО «Лютик»', '7736207543'), client(2, 'ИП Петров', '500100732259')],
    );
    const search = await screen.findByRole('searchbox');

    fireEvent.change(search, { target: { value: '7736' } });
    expect(screen.getByText('ООО «Лютик»')).toBeTruthy();
    expect(screen.queryByText('ИП Петров')).toBeNull();

    fireEvent.change(search, { target: { value: 'сидоров' } });
    expect(screen.getByText('Ничего не нашлось')).toBeTruthy();
  });

  it('creates the document from the chosen organization', async () => {
    const createDocument = setup([
      organization(1, 'ООО «Ромашка»', true),
      organization(2, 'ИП Нотченко', false),
    ]);

    fireEvent.click(await screen.findByText('ИП Нотченко'));
    fireEvent.click(screen.getByText('Ввести вручную'));

    await waitFor(() =>
      expect(createDocument).toHaveBeenCalledWith({
        template_id: 1,
        counterparty_id: null,
        organization_id: 2,
      }),
    );
  });

  it('does not ask «from whom» with a single organization and uses it', async () => {
    const createDocument = setup([organization(1, 'ООО «Ромашка»', true)]);

    fireEvent.click(await screen.findByText('Ввести вручную'));

    await waitFor(() =>
      expect(createDocument).toHaveBeenCalledWith(expect.objectContaining({ organization_id: 1 })),
    );
    expect(screen.queryByText('От кого')).toBeNull();
  });
});
