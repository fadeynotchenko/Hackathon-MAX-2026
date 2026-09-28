import { describe, expect, it } from 'vitest';

import { makeTemplate } from '@/test-utils';

import {
  draftFromTemplate,
  EMPTY_DRAFT,
  fieldsOf,
  insertText,
  keyFor,
  previewText,
  problemsOf,
  toRequest,
  withField,
} from './editor';

const draft = (text: string, title = 'Акт') => ({ ...EMPTY_DRAFT, title, text });

describe('template editor', () => {
  it('shows fields by name and stores them by key', () => {
    const template = makeTemplate({
      body: 'Счёт для {{client_name}}, ИНН {{client_inn}}\nИтого: {{total}}',
    });
    const loaded = draftFromTemplate(template, { copy: true });

    expect(loaded.text).toBe(
      'Счёт для {{Название клиента}}, ИНН {{ИНН клиента}}\nИтого: {{Сумма к оплате}}',
    );
    expect(loaded.title).toBe('Счёт на оплату (копия)');
    expect(loaded.kind).toBe('invoice');
    const request = toRequest(loaded);
    expect(request.body).toBe(template.body);
    expect(request.fields.map((field) => field.key)).toEqual([
      'client_name',
      'client_inn',
      'total',
    ]);
  });

  it('recognises catalog fields and makes keys for own ones', () => {
    const fields = fieldsOf(
      draft('{{инн  клиента}} {{Срок поставки}} {{Дата документа}} {{Срок поставки}}'),
    );

    expect(fields.map((field) => [field.key, field.type])).toEqual([
      ['client_inn', 'inn'],
      ['srok_postavki', 'text'],
      ['date', 'date'],
    ]);
    expect(fields[0]?.label).toBe('ИНН клиента');
    expect(fields[2]?.today_by_default).toBe(true);
  });

  it('keeps own keys readable, unique and away from requisite prefixes', () => {
    expect(keyFor('Адрес доставки', new Set())).toBe('adres_dostavki');
    expect(keyFor('Срок', new Set(['srok', 'srok_2']))).toBe('srok_3');
    expect(keyFor('Client name', new Set())).toBe('f_client_name');
    expect(keyFor('№', new Set())).toBe('field');
    expect(keyFor('2 этап', new Set())).toBe('f_2_etap');
  });

  it('treats two names of one key as one field', () => {
    const template = makeTemplate({
      body: 'Подписант: {{seller_director}}',
      fields: [
        {
          key: 'seller_director',
          label: 'Подписант',
          type: 'name',
          group: 'Продавец',
          required: false,
          hint: '',
          max_length: null,
          carry_over: true,
          today_by_default: false,
          default: '',
        },
      ],
    });
    const loaded = draftFromTemplate(template, { copy: false });
    const text = `${loaded.text}\n{{Подписант продавца}}`;

    const request = toRequest({ ...loaded, text });
    expect(request.body).toBe('Подписант: {{seller_director}}\n{{seller_director}}');
    expect(request.fields).toHaveLength(1);
  });

  it('remembers field settings by name', () => {
    const start = draft('Срок: {{Срок поставки}}');
    const [field] = fieldsOf(start);
    const changed = withField(start, { ...field!, type: 'date', required: false });

    expect(fieldsOf(changed)[0]).toMatchObject({ type: 'date', required: false });
    const removed = { ...changed, text: 'Без полей' };
    const back = { ...removed, text: 'Снова {{срок поставки}}' };
    expect(fieldsOf(back)[0]).toMatchObject({ key: field!.key, type: 'date' });
  });

  it('explains what blocks saving', () => {
    expect(problemsOf(draft('', ''))).toEqual(['Назовите шаблон', 'Напишите текст шаблона']);
    expect(problemsOf(draft('Просто текст'))).toEqual(['Вставьте в текст хотя бы одно поле']);
    expect(problemsOf(draft('Итого {{Сумма}}'))).toEqual([]);
  });

  it('inserts at the caret and previews blanks like the server', () => {
    expect(insertText('Итого:  руб.', { start: 7, end: 7 }, '{{Сумма}}')).toEqual({
      text: 'Итого: {{Сумма}} руб.',
      caret: 16,
    });
    expect(insertText('abc', { start: 10, end: 20 }, 'X')).toEqual({ text: 'abcX', caret: 4 });
    expect(previewText('Итого: {{Сумма}} руб.')).toBe('Итого: __________ руб.');
  });
});
