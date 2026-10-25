import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { activeScreen, makeDocument, makeTemplate, mockApi, renderScreen } from '@/test-utils';

import { DocumentPage } from './DocumentPage';

function open(kind: 'invoice' | 'act') {
  const api = mockApi();
  const doc = makeDocument({ template: makeTemplate({ kind }) });
  vi.spyOn(api, 'document').mockResolvedValue(doc);
  vi.spyOn(api, 'documentHistory').mockResolvedValue([]);
  renderScreen(<DocumentPage />, {
    api,
    path: '/documents/:documentId',
    route: `/documents/${doc.id}`,
  });
  return { api, doc };
}

describe('DocumentPage act', () => {
  it('makes an act from an invoice and opens its form', async () => {
    const { api, doc } = open('invoice');
    const act = vi.spyOn(api, 'createAct').mockResolvedValue(makeDocument({ id: 99 }));
    fireEvent.click(await within(activeScreen()).findByText('Сделать акт'));
    await waitFor(() =>
      expect(screen.getByTestId('location')).toHaveTextContent('/documents/99/fill'),
    );
    expect(act).toHaveBeenCalledWith(doc.id);
  });

  it('has no act button on an act', async () => {
    open('act');
    await within(activeScreen()).findByText('На основе этого');
    expect(within(activeScreen()).queryByText('Сделать акт')).toBeNull();
  });
});
