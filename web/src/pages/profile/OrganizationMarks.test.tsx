import { fireEvent, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { Organization } from '@/api/client';
import { mockApi, renderScreen } from '@/test-utils';

import { OrganizationMarks } from './OrganizationMarks';

const ORGANIZATION: Organization = {
  id: 3,
  name: 'ООО «Ромашка»',
  inn: '7728417603',
  values: {},
  is_default: true,
  created_at: '2026-10-01T00:00:00Z',
  updated_at: '2026-10-01T00:00:00Z',
  has_signature: false,
  has_stamp: true,
};

describe('OrganizationMarks', () => {
  it('uploads a signature and removes the stamp', async () => {
    const api = mockApi();
    vi.spyOn(api, 'organizationMark').mockResolvedValue(new Blob(['png'], { type: 'image/png' }));
    globalThis.URL.createObjectURL = vi.fn(() => 'blob:stamp');
    globalThis.URL.revokeObjectURL = vi.fn();
    const upload = vi
      .spyOn(api, 'setOrganizationMark')
      .mockResolvedValue({ ...ORGANIZATION, has_signature: true });
    const remove = vi
      .spyOn(api, 'deleteOrganizationMark')
      .mockResolvedValue({ ...ORGANIZATION, has_signature: true, has_stamp: false });
    const { container } = renderScreen(<OrganizationMarks organization={ORGANIZATION} />, {
      api,
      path: '/',
      route: '/',
    });

    expect(await screen.findByAltText('Печать')).toHaveAttribute('src', 'blob:stamp');
    const input = container.querySelector<HTMLInputElement>('input[type="file"]');
    expect(input).not.toBeNull();
    const file = new File(['jpg'], 'sign.jpg', { type: 'image/jpeg' });
    fireEvent.change(input!, { target: { files: [file] } });
    await waitFor(() => expect(upload).toHaveBeenCalledWith(3, 'signature', file));

    fireEvent.click(await screen.findByText('Убрать: печать'));
    await waitFor(() => expect(remove).toHaveBeenCalledWith(3, 'stamp'));
    expect(await screen.findByText('Загрузить: печать')).toBeInTheDocument();
  });
});
