import { describe, expect, it } from 'vitest';

import { matchesCard, matchesQuery } from './search';

describe('matchesQuery', () => {
  it('needs every word, in any order and case', () => {
    expect(matchesQuery(['Счёт за лендинг', 'ООО «Лютик»'], 'лютик СЧЕТ')).toBe(true);
    expect(matchesQuery(['Счёт за лендинг', 'ООО «Лютик»'], 'лютик договор')).toBe(false);
  });

  it('matches everything on an empty query and skips missing fields', () => {
    expect(matchesQuery([null, undefined], '   ')).toBe(true);
    expect(matchesQuery([null, 'Договор'], 'дог')).toBe(true);
  });
});

describe('matchesCard', () => {
  it('finds a card by INN and saved requisites, not only by name', () => {
    const card = {
      name: 'ООО «Лютик»',
      inn: '7736207543',
      values: { signer: 'Иванов Иван Иванович', address: 'Москва' },
    };
    expect(matchesCard(card, '7736')).toBe(true);
    expect(matchesCard(card, 'иванов')).toBe(true);
    expect(matchesCard(card, 'ромашка')).toBe(false);
  });
});
