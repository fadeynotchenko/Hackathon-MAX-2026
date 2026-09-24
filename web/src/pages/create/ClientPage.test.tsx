// Выбор сторон перед созданием: своя организация (если их несколько) и клиент.
import { fireEvent, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { Organization } from '@/api/client';
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

function setup(organizations: Organization[]) {
  const api = mockApi();
  vi.spyOn(api, 'counterparties').mockResolvedValue([]);
  vi.spyOn(api, 'organizations').mockResolvedValue(organizations);
  const createDocument = vi.spyOn(api, 'createDocument').mockResolvedValue(makeDocument({ id: 9 }));
  renderScreen(<ClientPage />, { api, path: '/create/:templateId/client', route: '/create/1/client' });
  return createDocument;
}

describe('ClientPage', () => {
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
