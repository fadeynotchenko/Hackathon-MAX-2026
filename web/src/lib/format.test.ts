import { describe, expect, it } from 'vitest';

import { makeTemplate } from '@/test-utils';

import {
  documentName,
  documentState,
  formatMoney,
  formatRelative,
  groupFields,
  initials,
  inputKind,
  pluralize,
} from './format';
import { startRoute } from './startRoute';

describe('format helpers', () => {
  it('formats money like the document does', () => {
    expect(formatMoney('120000.00')).toBe('120 000');
    expect(formatMoney('99.5')).toBe('99,50');
    expect(formatMoney('abc')).toBe('abc');
  });

  it('picks a keyboard by field type', () => {
    expect(inputKind('inn').inputMode).toBe('numeric');
    expect(inputKind('money')).toMatchObject({ inputMode: 'decimal', suffix: '₽' });
    expect(inputKind('date').type).toBe('date');
    expect(inputKind('multiline').multiline).toBe(true);
    expect(inputKind('address').multiline).toBe(true);
  });

  it('tells same-kind documents apart by number', () => {
    expect(documentName('Счёт на оплату', '17')).toBe('Счёт на оплату № 17');
    expect(documentName('Счёт на оплату', null)).toBe('Счёт на оплату');
    expect(documentName('Счёт № 17 для Альфы', '17')).toBe('Счёт № 17 для Альфы');
  });

  it('orders form sections: client, terms, own organization', () => {
    const groups = groupFields(makeTemplate().fields).map(([group]) => group);
    expect(groups).toEqual(['Клиент', 'Предмет', 'Продавец']);
  });

  it('describes a document by its latest sending', () => {
    expect(documentState({ status: 'draft', sent: null })).toEqual({
      label: 'Черновик',
      tone: 'draft',
    });
    expect(documentState({ status: 'ready', sent: null }).label).toBe('Готов');
    expect(
      documentState({
        status: 'ready',
        sent: { delivery: 'delivered', format: 'pdf', sent_at: '2026-09-24T10:00:00Z' },
      }).label,
    ).toBe('В чате PDF');
    expect(
      documentState({
        status: 'ready',
        sent: { delivery: 'failed', format: 'docx', sent_at: '2026-09-24T10:00:00Z' },
      }).tone,
    ).toBe('failed');
  });

  it('speaks russian plurals', () => {
    expect([1, 2, 5, 11, 21, 22].map((n) => pluralize(n, 'поле', 'поля', 'полей'))).toEqual([
      'поле',
      'поля',
      'полей',
      'полей',
      'поле',
      'поля',
    ]);
  });

  it('shows relative dates in lists', () => {
    const now = new Date('2026-09-24T15:00:00');
    expect(formatRelative('2026-09-24T09:05:00', now)).toBe('сегодня, 09:05');
    expect(formatRelative('2026-09-23T09:05:00', now)).toBe('вчера');
  });

  it('builds avatar letters without the legal form', () => {
    expect(initials('ООО «Альфа Строй»')).toBe('АС');
    expect(initials('ИП Иванов')).toBe('И');
  });

  it('maps start params from bot buttons to screens', () => {
    expect(startRoute('archive')).toBe('/archive');
    expect(startRoute('doc_42')).toBe('/documents/42');
    expect(startRoute('company')).toBe('/profile/organizations');
    expect(startRoute('unknown')).toBeNull();
    expect(startRoute(null)).toBeNull();
  });
});
