import { describe, expect, it } from 'vitest';

import { displayValue } from './format';
import { itemsTotal, parseItems, rowAmount, serializeItems, toNumber } from './items';

const SERVER = JSON.stringify([
  { name: 'Разработка сайта', quantity: '2', unit: 'усл.', price: '60000.00' },
  { name: 'Хостинг', quantity: '1.5', unit: 'мес.', price: '999.99' },
]);

describe('items', () => {
  it('reads the canonical server value with a decimal comma in quantity', () => {
    expect(parseItems(SERVER)).toEqual([
      { name: 'Разработка сайта', quantity: '2', unit: 'усл.', price: '60000.00' },
      { name: 'Хостинг', quantity: '1,5', unit: 'мес.', price: '999.99' },
    ]);
  });

  it('treats broken or non-list values as no rows', () => {
    expect(parseItems('')).toEqual([]);
    expect(parseItems('Разработка сайта')).toEqual([]);
    expect(parseItems('{"name": "x"}')).toEqual([]);
  });

  it('drops empty rows and gives an empty value when nothing is filled', () => {
    const empty = { name: '', quantity: '1', unit: '', price: '' };
    expect(serializeItems([empty])).toBe('');
    expect(
      JSON.parse(
        serializeItems([{ name: ' Монтаж ', quantity: '3', unit: 'ч', price: '1 500' }, empty]),
      ),
    ).toEqual([{ name: 'Монтаж', quantity: '3', unit: 'ч', price: '1 500' }]);
  });

  it('sums rows to kopecks like the server and skips rows without a price', () => {
    const rows = parseItems(SERVER);
    expect(rows.map(rowAmount)).toEqual([120000, 1499.99]);
    expect(itemsTotal([...rows, { name: 'Без цены', quantity: '1', unit: '', price: '' }])).toBe(
      121499.99,
    );
    expect(toNumber('1 500,50')).toBe(1500.5);
    expect(toNumber('abc')).toBeNull();
  });

  it('shows items as a numbered list on the review screen', () => {
    expect(displayValue('items', SERVER)).toBe(
      '1. Разработка сайта — 2 усл. × 60 000 ₽\n2. Хостинг — 1,5 мес. × 999,99 ₽',
    );
  });
});
