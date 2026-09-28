import { describe, expect, it } from 'vitest';

import type { DocumentSummary } from '@/api/client';

import { filterDocuments, groupDocuments, NO_CLIENT } from './archive';

function doc(overrides: Partial<DocumentSummary>): DocumentSummary {
  return {
    id: 1,
    title: 'Счёт',
    status: 'draft',
    template_title: 'Счёт на оплату',
    client: null,
    counterparty_name: null,
    number: null,
    sent: null,
    created_at: '2026-09-28T09:00:00Z',
    updated_at: '2026-09-28T09:00:00Z',
    ...overrides,
  };
}

const invoice = doc({ id: 1, client: 'ООО «Альфа»', number: '17' });
const offer = doc({
  id: 2,
  title: 'КП',
  template_title: 'Коммерческое предложение',
  client: 'ООО «Бета»',
  status: 'ready',
  updated_at: '2026-09-29T09:00:00Z',
});
const sent = doc({
  id: 3,
  client: 'ООО «Альфа»',
  sent: { format: 'pdf', delivery: 'failed' } as DocumentSummary['sent'],
  updated_at: '2026-09-20T09:00:00Z',
});
const kindOf = (item: DocumentSummary) =>
  item.template_title.startsWith('Счёт') ? 'invoice' : 'offer';

describe('my documents', () => {
  it('filters by search, status and kind, freshest first', () => {
    const all = [invoice, offer, sent];
    const pick = (filter: Partial<Parameters<typeof filterDocuments>[1]>) =>
      filterDocuments(all, { query: '', status: null, kind: null, kindOf, ...filter }).map(
        (item) => item.id,
      );
    expect(pick({})).toEqual([2, 1, 3]);
    expect(pick({ query: 'альфа' })).toEqual([1, 3]);
    expect(pick({ status: 'ready' })).toEqual([2]);
    // Не дошедший до чата ищут среди отправленных.
    expect(pick({ status: 'sent' })).toEqual([3]);
    expect(pick({ kind: 'invoice', status: 'draft' })).toEqual([1]);
  });

  it('groups by client or by day', () => {
    const now = new Date('2026-09-29T12:00:00');
    const loose = doc({ id: 4, updated_at: '2026-08-10T09:00:00Z' });
    const ordered = [offer, invoice, sent, loose];
    expect(groupDocuments(ordered, 'client', now).map(([title]) => title)).toEqual([
      'ООО «Бета»',
      'ООО «Альфа»',
      NO_CLIENT,
    ]);
    expect(groupDocuments(ordered, 'date', now).map(([title]) => title)).toEqual([
      'Сегодня',
      'Вчера',
      'сентябрь 2026 г.',
      'август 2026 г.',
    ]);
  });
});
