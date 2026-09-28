// Тестовые данные админа должны проходить проверку сервера. Правила сервера
// (core.domain.documents: normalize, _cross_field_errors, _bic_for) перенесены
// сюда отдельно от mock.ts — иначе генератор сверялся бы сам с собой.
import { describe, expect, it } from 'vitest';

import type { FieldSpec, FieldType } from '@/api/client';

import { mockValues } from './mock';

// Детерминированный генератор для повторяемых прогонов.
function seeded(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const SEEDS = Array.from({ length: 150 }, (_, index) => index + 1);
const TODAY = new Date(2026, 8, 28);

function spec(
  key: string,
  label: string,
  type: FieldType,
  extra: Partial<FieldSpec> = {},
): FieldSpec {
  return {
    key,
    label,
    type,
    group: '',
    required: true,
    hint: '',
    max_length: null,
    carry_over: true,
    today_by_default: false,
    ...extra,
  };
}

// Встроенные шаблоны — копия core/src/core/usecases/documents/builtin.py.
const SELLER = { group: 'Продавец' };
const CLIENT = { group: 'Клиент' };
const SUBJECT = { group: 'Предмет' };
const OPTIONAL = { required: false };

const SELLER_REQUISITES = [
  spec('seller_name', 'Название продавца', 'text', SELLER),
  spec('seller_inn', 'ИНН продавца', 'inn', SELLER),
  spec('seller_kpp', 'КПП продавца', 'kpp', { ...SELLER, ...OPTIONAL }),
  spec('seller_address', 'Адрес продавца', 'address', { ...SELLER, ...OPTIONAL }),
];

const INVOICE = [
  spec('number', 'Номер счёта', 'text', { ...SUBJECT, max_length: 32, carry_over: false }),
  spec('date', 'Дата счёта', 'date', { ...SUBJECT, carry_over: false, today_by_default: true }),
  ...SELLER_REQUISITES,
  spec('seller_bank', 'Банк', 'text', SELLER),
  spec('seller_bic', 'БИК', 'bic', SELLER),
  spec('seller_account', 'Расчётный счёт', 'account', SELLER),
  spec('client_name', 'Название клиента', 'text', CLIENT),
  spec('client_inn', 'ИНН клиента', 'inn', { ...CLIENT, ...OPTIONAL }),
  spec('client_address', 'Адрес клиента', 'address', { ...CLIENT, ...OPTIONAL }),
  spec('item', 'Наименование работ или услуг', 'multiline', SUBJECT),
  spec('total', 'Сумма к оплате', 'money', SUBJECT),
  spec('vat', 'НДС', 'text', {
    ...SUBJECT,
    ...OPTIONAL,
    hint: '«Без НДС» или, например, «20% — 20 000,00»',
  }),
  spec('due_date', 'Оплатить до', 'date', { ...SUBJECT, ...OPTIONAL, carry_over: false }),
  spec('seller_director', 'Подписант', 'name', { ...SELLER, ...OPTIONAL }),
];

const OFFER = [
  spec('date', 'Дата предложения', 'date', { ...SUBJECT, carry_over: false }),
  spec('seller_name', 'Название продавца', 'text', SELLER),
  spec('seller_phone', 'Телефон', 'phone', { ...SELLER, ...OPTIONAL }),
  spec('seller_email', 'Почта', 'email', { ...SELLER, ...OPTIONAL }),
  spec('client_name', 'Название клиента', 'text', CLIENT),
  spec('subject', 'Тема предложения', 'text', SUBJECT),
  spec('scope', 'Состав работ', 'multiline', SUBJECT),
  spec('total', 'Стоимость', 'money', SUBJECT),
  spec('term', 'Срок выполнения', 'text', { ...SUBJECT, ...OPTIONAL }),
  spec('valid_until', 'Предложение действует до', 'date', { ...SUBJECT, carry_over: false }),
];

const CONTRACT = [
  spec('number', 'Номер договора', 'text', { ...SUBJECT, max_length: 32, carry_over: false }),
  spec('date', 'Дата договора', 'date', { ...SUBJECT, carry_over: false }),
  spec('city', 'Город', 'text', SUBJECT),
  ...SELLER_REQUISITES,
  spec('seller_director', 'Подписант продавца', 'name', SELLER),
  spec('client_name', 'Название клиента', 'text', CLIENT),
  spec('client_inn', 'ИНН клиента', 'inn', CLIENT),
  spec('client_director', 'Подписант клиента', 'name', { ...CLIENT, ...OPTIONAL }),
  spec('subject', 'Предмет договора', 'multiline', SUBJECT),
  spec('total', 'Стоимость услуг', 'money', SUBJECT),
  spec('term_days', 'Срок оказания, дней', 'integer', SUBJECT),
  spec('payment_days', 'Срок оплаты, дней', 'integer', { ...SUBJECT, ...OPTIONAL }),
];

const BUILTIN = { invoice: INVOICE, offer: OFFER, contract: CONTRACT };

// Record по FieldType: новый тип поля без строки здесь не соберётся.
const TYPE_LABEL: Record<FieldType, string> = {
  text: 'Объект',
  multiline: 'Особые условия',
  name: 'Ответственный',
  address: 'Адрес доставки',
  email: 'Почта',
  phone: 'Телефон',
  money: 'Сумма',
  date: 'Дата',
  integer: 'Количество',
  inn: 'ИНН',
  kpp: 'КПП',
  ogrn: 'ОГРН',
  bic: 'БИК',
  account: 'Расчётный счёт',
};
const EVERY_TYPE = (Object.entries(TYPE_LABEL) as Array<[FieldType, string]>).map(([type, label]) =>
  spec(`custom_${type}`, label, type, OPTIONAL),
);

// --- правила сервера ------------------------------------------------------

const digitsOf = (value: string) => value.replace(/[^0-9]+/g, '');

function innValid(value: string): boolean {
  const check = (weights: number[]) =>
    (weights.reduce((sum, weight, index) => sum + weight * Number(value[index]), 0) % 11) % 10;
  if (value.length === 10) return check([2, 4, 10, 3, 5, 9, 4, 6, 8]) === Number(value[9]);
  if (value.length === 12) {
    return (
      check([7, 2, 4, 10, 3, 5, 9, 4, 6, 8]) === Number(value[10]) &&
      check([3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]) === Number(value[11])
    );
  }
  return false;
}

function ogrnValid(value: string): boolean {
  if (value.length === 13)
    return (BigInt(value.slice(0, 12)) % 11n) % 10n === BigInt(value[12] ?? '');
  if (value.length === 15)
    return (BigInt(value.slice(0, 14)) % 13n) % 10n === BigInt(value[14] ?? '');
  return false;
}

function accountKeyValid(account: string, bic: string): boolean {
  if (account.length !== 20 || bic.length !== 9) return false;
  const prefix = account.startsWith('0') ? `0${bic.slice(4, 6)}` : bic.slice(6, 9);
  const weights = [7, 1, 3];
  const sum = [...(prefix + account)].reduce(
    (total, digit, index) => total + Number(digit) * (weights[index % 3] ?? 0),
    0,
  );
  return sum % 10 === 0;
}

const sideOf = (key: string) => (key.includes('_') ? key.slice(0, key.lastIndexOf('_')) : '');

function bicFor(accountKey: string, bicKeys: string[]): string | undefined {
  const same = bicKeys.filter((key) => sideOf(key) === sideOf(accountKey));
  if (same.length > 0) return same[0];
  return bicKeys.length === 1 ? bicKeys[0] : undefined;
}

const KPP = /^[0-9]{4}[0-9A-Z]{2}[0-9]{3}$/;
const EMAIL = /^[^@\s]+@[^@\s.]+\.[^@\s]+$/;
const INTEGER = /^\+?([0-9][0-9 ]*?)\s*[а-яёa-z.]*$/i;
// Служебные символы, кроме табуляции и переводов строки, — как _CONTROL сервера.
const hasControl = (value: string) =>
  [...value].some((char) => {
    const code = char.charCodeAt(0);
    return (code < 32 && ![9, 10, 13].includes(code)) || code === 127;
  });

function isoValid(value: string): boolean {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return false;
  const [year, month, day] = [Number(match[1]), Number(match[2]), Number(match[3])];
  const date = new Date(year, month - 1, day);
  return year >= 1900 && year <= 2100 && date.getMonth() === month - 1 && date.getDate() === day;
}

function moneyValid(value: string): boolean {
  const cleaned = value.replace(/\s+/g, '').replace(',', '.');
  return /^[0-9]+(\.[0-9]{1,2})?$/.test(cleaned) && Number(cleaned) <= 999_999_999_999.99;
}

function limitOf(field: FieldSpec): number {
  const byType: Partial<Record<FieldType, number>> = { multiline: 5000, email: 254 };
  return field.max_length || byType[field.type] || 1000;
}

function typeValid(field: FieldSpec, value: string): boolean {
  const digits = digitsOf(value);
  switch (field.type) {
    case 'money':
      return moneyValid(value);
    case 'date':
      return isoValid(value);
    case 'integer': {
      const match = INTEGER.exec(value);
      return match !== null && digitsOf(match[1] ?? '').length <= 9;
    }
    case 'email':
      return EMAIL.test(value);
    case 'phone':
      return (digits.length === 11 && /^[78]/.test(digits)) || digits.length === 10;
    case 'inn':
      return innValid(digits);
    case 'kpp':
      return KPP.test(value.toUpperCase().replace(/[^0-9A-Z]/g, ''));
    case 'ogrn':
      return ogrnValid(digits);
    case 'bic':
      return digits.length === 9 && digits.startsWith('04');
    case 'account':
      return digits.length === 20;
    default:
      return true;
  }
}

// Замечания сервера к набору значений; пустое значение — тоже замечание:
// кнопка заполняет все поля, и обязательные, и нет.
function serverErrors(fields: FieldSpec[], values: Record<string, string>): string[] {
  const errors: string[] = [];
  for (const field of fields) {
    const value = (values[field.key] ?? '').trim();
    if (!value) errors.push(`${field.key}: пусто`);
    else if (hasControl(value)) errors.push(`${field.key}: служебные символы`);
    else if ([...value].length > limitOf(field)) errors.push(`${field.key}: длиннее предела`);
    else if (!typeValid(field, value)) errors.push(`${field.key}: ${field.type} «${value}»`);
  }
  const bicKeys = fields.filter((field) => field.type === 'bic').map((field) => field.key);
  for (const field of fields.filter((item) => item.type === 'account')) {
    const bicKey = bicFor(field.key, bicKeys);
    if (bicKey === undefined) continue;
    const account = digitsOf(values[field.key] ?? '');
    if (!accountKeyValid(account, digitsOf(values[bicKey] ?? ''))) {
      errors.push(`${field.key}: счёт не сходится с ${bicKey}`);
    }
  }
  return errors;
}

const generate = (fields: FieldSpec[], seed: number) =>
  mockValues(fields, { random: seeded(seed), today: TODAY });

describe('mockValues — тестовые данные для админа', () => {
  it.each(Object.entries(BUILTIN))(
    'fills every %s field with values the server accepts',
    (_, fields) => {
      for (const seed of SEEDS) {
        const values = generate(fields, seed);
        expect(Object.keys(values)).toEqual(fields.map((field) => field.key));
        expect(serverErrors(fields, values)).toEqual([]);
      }
    },
  );

  it('gives every field type a non-empty valid value', () => {
    for (const seed of SEEDS) {
      const values = generate(EVERY_TYPE, seed);
      for (const field of EVERY_TYPE) expect(values[field.key]?.trim()).toBeTruthy();
      expect(serverErrors(EVERY_TYPE, values)).toEqual([]);
    }
  });

  it('computes INN and OGRN checksums: 10/13 digits for companies, 12/15 for sole traders', () => {
    const fields = [
      spec('seller_name', 'Название продавца', 'text'),
      spec('seller_inn', 'ИНН продавца', 'inn'),
      spec('seller_ogrn', 'ОГРН продавца', 'ogrn'),
      spec('client_name', 'Название клиента', 'text'),
      spec('client_inn', 'ИНН клиента', 'inn'),
      spec('client_ogrn', 'ОГРН клиента', 'ogrn'),
    ];
    const lengths = new Set<number>();
    for (const seed of SEEDS) {
      const values = generate(fields, seed);
      for (const side of ['seller', 'client']) {
        const inn = values[`${side}_inn`] ?? '';
        const ogrn = values[`${side}_ogrn`] ?? '';
        const sole = (values[`${side}_name`] ?? '').startsWith('ИП ');
        expect(innValid(inn), inn).toBe(true);
        expect(ogrnValid(ogrn), ogrn).toBe(true);
        expect(inn).toHaveLength(sole ? 12 : 10);
        expect(ogrn).toHaveLength(sole ? 15 : 13);
        lengths.add(inn.length);
      }
    }
    expect([...lengths].sort()).toEqual([10, 12]);
  });

  it('makes a side with a KPP field a company and builds KPP from its tax office', () => {
    for (const seed of SEEDS) {
      const values = generate(CONTRACT, seed);
      const kpp = values['seller_kpp'] ?? '';
      expect(kpp).toMatch(KPP);
      expect(kpp.slice(0, 4)).toBe(values['seller_inn']?.slice(0, 4));
      expect(values['seller_inn']).toHaveLength(10);
      expect(values['seller_name']).toMatch(/^(ООО|АО) «.+»$/);
    }
  });

  it('keys each account to the BIC of its own side', () => {
    const twoSides = [
      spec('seller_bic', 'БИК продавца', 'bic'),
      spec('seller_account', 'Счёт продавца', 'account'),
      spec('client_account', 'Счёт клиента', 'account'),
      spec('client_bic', 'БИК клиента', 'bic'),
    ];
    // Один БИК на шаблон: сервер сверяет с ним любой счёт, даже чужой стороны.
    const singleBic = [
      spec('bic', 'БИК', 'bic'),
      spec('account', 'Расчётный счёт', 'account'),
      spec('client_account', 'Счёт клиента', 'account'),
    ];
    for (const seed of SEEDS) {
      const two = generate(twoSides, seed);
      expect(accountKeyValid(two['seller_account'] ?? '', two['seller_bic'] ?? '')).toBe(true);
      expect(accountKeyValid(two['client_account'] ?? '', two['client_bic'] ?? '')).toBe(true);
      expect(two['seller_account']).toMatch(/^40[78]02810\d{12}$/);
      const single = generate(singleBic, seed);
      expect(accountKeyValid(single['account'] ?? '', single['bic'] ?? '')).toBe(true);
      expect(accountKeyValid(single['client_account'] ?? '', single['bic'] ?? '')).toBe(true);
    }
  });

  it('keeps every value within max_length', () => {
    const tight = [
      spec('number', 'Номер', 'text', { max_length: 2 }),
      spec('seller_name', 'Название', 'text', { max_length: 5 }),
      spec('scope', 'Состав работ', 'multiline', { max_length: 40 }),
      spec('subject', 'Предмет договора', 'multiline', { max_length: 30 }),
      spec('vat', 'НДС', 'text', { max_length: 7 }),
      spec('client_address', 'Адрес', 'address', { max_length: 15 }),
    ];
    for (const seed of SEEDS) {
      const values = generate(tight, seed);
      for (const field of tight) {
        const value = values[field.key] ?? '';
        expect(value.trim()).not.toBe('');
        expect([...value].length).toBeLessThanOrEqual(field.max_length ?? 0);
      }
    }
  });

  it('is deterministic for one seed and varies across seeds', () => {
    expect(generate(INVOICE, 42)).toEqual(generate(INVOICE, 42));
    const variants = new Set(SEEDS.map((seed) => JSON.stringify(generate(INVOICE, seed))));
    expect(variants.size).toBe(SEEDS.length);
    const sellers = new Set(SEEDS.map((seed) => generate(INVOICE, seed)['seller_name']));
    expect(sellers.size).toBeGreaterThan(5);
  });

  it('dates the document today and deadlines 5–30 days ahead, in ISO like the date input', () => {
    const earliest = '2026-10-03';
    const latest = '2026-10-28';
    for (const seed of SEEDS) {
      const invoice = generate(INVOICE, seed);
      const due = invoice['due_date'] ?? '';
      expect(invoice['date']).toBe('2026-09-28');
      expect(due >= earliest && due <= latest, due).toBe(true);
      const offer = generate(OFFER, seed);
      const until = offer['valid_until'] ?? '';
      expect(offer['date']).toBe('2026-09-28');
      expect(until >= earliest && until <= latest, until).toBe(true);
    }
  });

  it('takes the seller and the client from different organisations', () => {
    for (const seed of SEEDS) {
      const values = generate(INVOICE, seed);
      expect(values['client_name']).not.toBe(values['seller_name']);
      expect(values['client_inn']).not.toBe(values['seller_inn']);
      expect(values['seller_director']).not.toBe('');
    }
  });

  it('keeps VAT consistent with the total and amounts round', () => {
    const format = (kopecks: number) =>
      `${String(Math.floor(kopecks / 100)).replace(/\B(?=(\d{3})+(?!\d))/g, ' ')},${String(kopecks % 100).padStart(2, '0')}`;
    for (const seed of SEEDS) {
      const values = generate(INVOICE, seed);
      const total = Number((values['total'] ?? '').replace(/\s/g, ''));
      expect(total % 1000).toBe(0);
      expect(total).toBeGreaterThanOrEqual(10_000);
      expect(total).toBeLessThanOrEqual(500_000);
      const vat = values['vat'];
      if (vat !== 'Без НДС') expect(vat).toBe(`20% — ${format(Math.round((total * 100) / 6))}`);
    }
  });

  it('reads meaning from labels of own templates with transliterated keys', () => {
    const fields = [
      spec('summa', 'Сумма', 'money'),
      spec('summa_propisyu', 'Сумма прописью', 'text'),
      spec('srok_postavki', 'Срок поставки', 'text'),
      spec('kontaktnoe_litso', 'Контактное лицо', 'text'),
      spec('srok_oplaty_dney', 'Срок оплаты, дней', 'integer'),
    ];
    const values = generate(fields, 7);
    expect(values['summa_propisyu']).toMatch(/^[А-Я][а-я ]+ рублей 00 копеек$/);
    expect(values['srok_postavki']).toMatch(/дн|недел|месяц/);
    expect(values['kontaktnoe_litso']).toMatch(/^[А-ЯЁ][а-яё]+ [А-ЯЁ][а-яё]+ [А-ЯЁ][а-яё]+$/);
    expect(Number(values['srok_oplaty_dney'])).toBeGreaterThanOrEqual(1);
    expect(Number(values['srok_oplaty_dney'])).toBeLessThanOrEqual(60);
  });

  it('works with the real clock and Math.random', () => {
    const now = new Date();
    const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
    const values = mockValues(CONTRACT);
    expect(serverErrors(CONTRACT, values)).toEqual([]);
    expect(values['date']).toBe(today);
  });
});
