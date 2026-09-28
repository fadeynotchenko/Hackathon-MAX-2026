import { describe, expect, it } from 'vitest';

import { makeTemplate } from '@/test-utils';

import { catalogSections, catalogTags } from './catalog';

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

  it('keeps the kind sections while searching a split catalog', () => {
    const selfEmployed = makeTemplate({ id: 4, kind: 'contract', title: 'С самозанятым' });
    const catalog = [contract, selfEmployed, offer, invoice];
    expect(catalogSections([invoice], catalog)).toEqual([['Счета', [invoice]]]);
  });

  it('drops a section the search left empty', () => {
    expect(catalogSections([ownOffer])).toEqual([['Мои шаблоны', [ownOffer]]]);
  });

  it('splits the standard ones by kind when a kind has several variants', () => {
    const selfEmployed = makeTemplate({
      id: 4,
      kind: 'contract',
      title: 'Договор оказания услуг: с самозанятым',
    });
    expect(catalogSections([contract, selfEmployed, offer, invoice, ownOffer])).toEqual([
      ['Мои шаблоны', [ownOffer]],
      ['Счета', [invoice]],
      ['Коммерческие предложения', [offer]],
      ['Договоры', [contract, selfEmployed]],
    ]);
  });

  it('offers «Мои» and the kinds present, in section order', () => {
    expect(catalogTags([contract, offer, invoice, ownOffer]).map((tag) => tag.title)).toEqual([
      'Мои',
      'Счета',
      'КП',
      'Договоры',
    ]);
    expect(catalogTags([contract]).map((tag) => tag.value)).toEqual(['contract']);
  });
});
