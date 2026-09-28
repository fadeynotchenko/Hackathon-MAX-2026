import { describe, expect, it } from 'vitest';

import { makeTemplate } from '@/test-utils';

import { catalogSections } from './catalog';

const invoice = makeTemplate({ id: 1, kind: 'invoice', title: 'Счёт на оплату' });
const offer = makeTemplate({ id: 2, kind: 'offer', title: 'Коммерческое предложение' });
const contract = makeTemplate({ id: 3, kind: 'contract', title: 'Договор оказания услуг' });
const ownOffer = makeTemplate({ id: 7, kind: 'offer', title: 'Фирменный КП', is_builtin: false });
const ownAct = makeTemplate({ id: 8, kind: 'other', title: 'Акт', is_builtin: false });

describe('catalog sections', () => {
  it('labels the standard templates even without own ones', () => {
    expect(catalogSections([contract, offer, invoice])).toEqual([
      ['Стандартные', [contract, offer, invoice]],
    ]);
    expect(catalogSections([])).toEqual([]);
  });

  it('puts own templates above the standard ones in server order', () => {
    expect(catalogSections([contract, offer, invoice, ownAct, ownOffer])).toEqual([
      ['Мои шаблоны', [ownAct, ownOffer]],
      ['Стандартные', [contract, offer, invoice]],
    ]);
  });

  it('drops a section the search left empty', () => {
    expect(catalogSections([ownOffer])).toEqual([['Мои шаблоны', [ownOffer]]]);
  });
});
