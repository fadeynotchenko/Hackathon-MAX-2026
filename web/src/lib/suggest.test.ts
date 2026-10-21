import { describe, expect, it } from 'vitest';

import { SIDE_PREFIXES, suggestTarget, suggestionValues } from './suggest';

const COMPANY = {
  title: 'ООО «Ромашка»',
  subtitle: 'ИНН 7707083893',
  values: { name: 'ООО «Ромашка»', inn: '7707083893', kpp: '773601001', director: 'Иванов' },
};

describe('suggestTarget', () => {
  it('finds the kind by key without the side prefix', () => {
    expect(suggestTarget('client_inn', 'inn', SIDE_PREFIXES)).toEqual({
      kind: 'company',
      prefix: 'client_',
    });
    expect(suggestTarget('seller_bic', 'bic', SIDE_PREFIXES)).toEqual({
      kind: 'bank',
      prefix: 'seller_',
    });
    expect(suggestTarget('name', 'text', [''])).toEqual({ kind: 'company', prefix: '' });
  });

  it('suggests addresses by type and leaves other fields alone', () => {
    expect(suggestTarget('delivery_address', 'address', SIDE_PREFIXES)?.kind).toBe('address');
    // Без префикса стороны «name» в документе — не организация.
    expect(suggestTarget('name', 'text', SIDE_PREFIXES)).toBeNull();
    expect(suggestTarget('client_kpp', 'kpp', SIDE_PREFIXES)).toBeNull();
  });
});

describe('suggestionValues', () => {
  it('fills only the side fields the template has', () => {
    const keys = new Set(['client_name', 'client_inn', 'seller_inn']);
    expect(
      suggestionValues({ kind: 'company', prefix: 'client_' }, 'client_inn', COMPANY, keys),
    ).toEqual({ client_name: 'ООО «Ромашка»', client_inn: '7707083893' });
  });

  it('takes every key in a requisites card', () => {
    expect(suggestionValues({ kind: 'company', prefix: '' }, 'inn', COMPANY, null)).toEqual(
      COMPANY.values,
    );
  });

  it('puts an address into the field it was searched from', () => {
    const address = { title: 'г Москва', subtitle: '', values: { address: '125009, г Москва' } };
    expect(
      suggestionValues({ kind: 'address', prefix: '' }, 'delivery_address', address, null),
    ).toEqual({ delivery_address: '125009, г Москва' });
  });
});
