import { describe, expect, it } from 'vitest';

import { innValid, ogrnValid, requisiteProblem } from './requisites';

// Демо-реквизиты ядра (core.usecases.documents.demo): сходятся по всем проверкам.
describe('requisites', () => {
  it('checks INN of a company and of a person', () => {
    expect(innValid('7728417603')).toBe(true);
    expect(innValid('7728 417 603')).toBe(true);
    expect(innValid('7728417604')).toBe(false);
    expect(innValid('500100732259')).toBe(true);
    expect(innValid('500100732258')).toBe(false);
    expect(innValid('12345')).toBe(false);
  });

  it('checks OGRN and OGRNIP', () => {
    expect(ogrnValid('1177746012344')).toBe(true);
    expect(ogrnValid('1177746012345')).toBe(false);
    expect(ogrnValid('304500116000157')).toBe(true);
  });

  it('explains the problem in the server words, empty is fine', () => {
    expect(requisiteProblem('inn', '')).toBeNull();
    expect(requisiteProblem('inn', '1234567890')).toBe('ИНН не проходит проверку');
    expect(requisiteProblem('kpp', '77280100')).toBe('КПП из 9 цифр');
    expect(requisiteProblem('kpp', '7728AB001')).toBeNull();
    expect(requisiteProblem('bic', '144525225')).toBe('БИК банка начинается с 04');
    expect(requisiteProblem('bic', '04452522')).toBe('БИК из 9 цифр');
    expect(requisiteProblem('account', '40702810538000123456')).toBeNull();
    expect(requisiteProblem('account', '407028105')).toBe('Счёт из 20 цифр');
    expect(requisiteProblem('text', 'что угодно')).toBeNull();
  });
});
