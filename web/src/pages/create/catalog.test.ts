import { describe, expect, it } from 'vitest';

import { makeTemplate } from '@/test-utils';

import { catalogSections } from './catalog';

const invoice = makeTemplate({ id: 1, kind: 'invoice', title: 'Счёт на оплату' });
const offer = makeTemplate({ id: 2, kind: 'offer', title: 'Коммерческое предложение' });
const contract = makeTemplate({ id: 3, kind: 'contract', title: 'Договор оказания услуг' });

describe('catalog sections', () => {
  it('keeps one grid while there are only standard templates', () => {
    expect(catalogSections([contract, offer, invoice])).toEqual([
      ['Шаблоны', [contract, offer, invoice]],
    ]);
    expect(catalogSections([])).toEqual([]);
  });

  it('puts own templates next to the standard ones of the same kind', () => {
    const ownOffer = makeTemplate({
      id: 7,
      kind: 'offer',
      title: 'Фирменный КП',
      is_builtin: false,
    });
    const ownAct = makeTemplate({ id: 8, kind: 'other', title: 'Акт', is_builtin: false });

    expect(catalogSections([contract, offer, invoice, ownAct, ownOffer])).toEqual([
      ['Счета', [invoice]],
      ['Коммерческие предложения', [offer, ownOffer]],
      ['Договоры', [contract]],
      ['Другие документы', [ownAct]],
    ]);
  });
});
