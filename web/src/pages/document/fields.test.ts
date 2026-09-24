import { describe, expect, it } from 'vitest';

import { makeDocument } from '@/test-utils';

import {
  changedValues,
  defaultCoverText,
  documentCaption,
  fragmentLabel,
  draftFromDocument,
  fieldErrors,
  mergeAfterSave,
  sourceOf,
  stripLabel,
} from './fields';

describe('document form state', () => {
  it('shows money in russian format and empty strings for missing fields', () => {
    const doc = makeDocument({
      values: {
        total: {
          value: '120000.00',
          source: 'agent',
          confirmed: false,
          fragment: null,
          confidence: null,
        },
      },
    });
    expect(draftFromDocument(doc)).toEqual({
      client_name: '',
      client_inn: '',
      total: '120 000',
      seller_name: '',
    });
  });

  it('sends only the fields a person changed', () => {
    expect(changedValues({ a: '1', b: ' 2 ', c: 'new' }, { a: '1', b: '2', c: '' })).toEqual({
      c: 'new',
    });
  });

  it('keeps rejected input for correction and takes the rest from the server', () => {
    const doc = makeDocument({
      values: {
        client_name: {
          value: 'ООО «Альфа»',
          source: 'manual',
          confirmed: true,
          fragment: null,
          confidence: null,
        },
      },
      errors: [
        {
          key: 'client_inn',
          code: 'field.inn_invalid',
          message: '«ИНН клиента»: ИНН не проходит проверку',
        },
      ],
    });
    const merged = mergeAfterSave(doc, { client_name: 'ооо альфа', client_inn: '123', total: '' });
    expect(merged['client_name']).toBe('ООО «Альфа»');
    expect(merged['client_inn']).toBe('123');
  });

  it('puts error text under the field without repeating its label', () => {
    expect(stripLabel('«ИНН клиента»: ИНН не проходит проверку')).toBe('ИНН не проходит проверку');
    const doc = makeDocument({
      errors: [
        {
          key: 'client_inn',
          code: 'field.inn_invalid',
          message: '«ИНН клиента»: ИНН не проходит проверку',
        },
      ],
    });
    expect(fieldErrors(doc, false)).toEqual({ client_inn: 'ИНН не проходит проверку' });
    expect(fieldErrors(doc, true)).toEqual({
      client_inn: 'ИНН не проходит проверку',
      client_name: 'Заполните поле',
      total: 'Заполните поле',
    });
  });

  it('marks recognized values as drafts until confirmed', () => {
    const doc = makeDocument({
      values: {
        total: {
          value: '1.00',
          source: 'ocr',
          confirmed: false,
          fragment: 'Итого 1,00',
          confidence: 0.8,
        },
        seller_name: {
          value: 'ООО «Мастер»',
          source: 'profile',
          confirmed: true,
          fragment: null,
          confidence: null,
        },
      },
    });
    const [client, , total, seller] = doc.template.fields;
    expect(sourceOf(doc, total!)).toEqual({ label: 'С фото · проверьте', draft: true });
    expect(sourceOf(doc, seller!)).toEqual({ label: 'Из организации', draft: false });
    expect(sourceOf(doc, client!)).toBeNull();
  });

  it('writes a neutral cover text without declining the client name', () => {
    const doc = makeDocument({
      values: {
        number: { value: '17', source: 'manual', confirmed: true, fragment: null, confidence: null },
        client_name: {
          value: 'Акционерное общество «Альфа»',
          source: 'counterparty',
          confirmed: true,
          fragment: null,
          confidence: null,
        },
      },
    });
    expect(defaultCoverText(doc)).toContain('Направляю счёт на оплату № 17.');
    expect(defaultCoverText(doc)).not.toContain('для Акционерное');
  });

  it('captions a document without repeating its kind', () => {
    const value = (v: string) => ({
      value: v,
      source: 'manual' as const,
      confirmed: true,
      fragment: null,
      confidence: null,
    });
    const plain = makeDocument({
      title: 'Счёт на оплату',
      values: { number: value('17'), client_name: value('ООО «Альфа»') },
    });
    expect(documentCaption(plain)).toBe('Счёт на оплату № 17 · ООО «Альфа»');
    const named = makeDocument({ title: 'Счёт для Альфы', values: {} });
    expect(documentCaption(named)).toBe('Счёт для Альфы · Счёт на оплату');
  });

  it('says where a value to confirm was read from', () => {
    expect(fragmentLabel('ocr', 'ИНН 7707083893')).toBe('На фото: «ИНН 7707083893»');
    expect(fragmentLabel('agent', 'на 120 тысяч')).toBe('В сообщении: «на 120 тысяч»');
  });
});
