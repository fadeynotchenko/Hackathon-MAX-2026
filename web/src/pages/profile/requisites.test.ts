import { describe, expect, it } from 'vitest';

import { splitRequisiteErrors } from './requisites';

describe('splitRequisiteErrors', () => {
  it('spreads server errors over the fields they name', () => {
    const { byField, rest } = splitRequisiteErrors(
      '«ИНН»: ИНН не проходит проверку; «Расчётный счёт»: счёт из 20 цифр; Что-то ещё',
    );
    expect(byField).toEqual({ inn: 'ИНН не проходит проверку', account: 'счёт из 20 цифр' });
    expect(rest).toEqual(['Что-то ещё']);
  });
});
