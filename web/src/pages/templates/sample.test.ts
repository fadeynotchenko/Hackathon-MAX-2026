import { describe, expect, it } from 'vitest';

import type { TemplateImport } from '@/api/client';

import { catalogByKey } from './editor';
import {
  addPlace,
  draftFromImport,
  labelText,
  markedInFile,
  placeFound,
  placeSpans,
  sampleRequest,
  toTextDraft,
  withoutField,
} from './sample';

const imported: TemplateImport = {
  file_id: 9,
  filename: 'КП.docx',
  format: 'docx',
  title: 'Коммерческое предложение',
  text: 'ООО «Мастер»\nДля: ООО «Альфа»\nСтоимость: 180 000 руб.\nЗаказчик: ________ Исполнитель: ________',
  found_by: 'assistant',
  kind: 'offer',
  notice: null,
  fields: [
    {
      key: 'client_name',
      label: 'Клиент',
      type: 'text',
      required: true,
      places: [{ text: 'ООО «Альфа»', before: '' }],
    },
    { key: 'seller_inn', label: 'ИНН', type: 'inn', required: true, places: [] },
    {
      key: '',
      label: 'Стоимость работ',
      type: 'money',
      required: true,
      places: [{ text: '180 000', before: '' }],
    },
    {
      key: '',
      label: 'Подписант клиента',
      type: 'name',
      required: false,
      places: [{ text: '________', before: 'Заказчик: ' }],
    },
    {
      key: 'seller_name',
      label: 'Мы',
      type: 'text',
      required: true,
      places: [{ text: 'ООО «Мастер»', before: '' }],
    },
  ],
};

describe('template from a sample file', () => {
  it('finds places like the server: longer first, context kept', () => {
    const line = 'Заказчик: ООО «Альфа Плюс», исполнитель: ________, подпись: ________';
    expect(
      placeSpans(line, [
        ['short', { text: 'Альфа', before: '' }],
        ['client_name', { text: 'ООО «Альфа Плюс»', before: '' }],
        ['seller_director', { text: '________', before: 'исполнитель: ' }],
      ]),
    ).toEqual([
      [10, 26, 'client_name'],
      [41, 49, 'seller_director'],
    ]);
  });

  it('turns an import into fields with catalog names and own keys', () => {
    const draft = draftFromImport(imported);

    expect(draft.fields.map((field) => [field.key, field.label, field.type])).toEqual([
      ['client_name', 'Название клиента', 'text'],
      ['stoimost_rabot', 'Стоимость работ', 'money'],
      ['client_director', 'Подписант клиента', 'name'],
      ['seller_name', 'Название продавца', 'text'],
    ]);
    expect(labelText(draft)).toBe(
      '{{Название продавца}}\nДля: {{Название клиента}}\nСтоимость: {{Стоимость работ}} руб.\n' +
        'Заказчик: {{Подписант клиента}} Исполнитель: ________',
    );
  });

  it('marks and unmarks places', () => {
    const draft = draftFromImport(imported);
    expect(placeFound(draft.text, { text: 'Исполнитель: ________', before: '' })).toBe(true);
    expect(placeFound(draft.text, { text: 'ООО «Гамма»', before: '' })).toBe(false);

    const marked = addPlace(draft, 'Подписант продавца', {
      text: '________',
      before: 'Исполнитель: ',
    });
    expect(marked.fields.at(-1)).toMatchObject({ key: 'seller_director', type: 'name' });
    const again = addPlace(marked, 'название клиента', { text: 'Альфа', before: '' });
    expect(again.fields.find((f) => f.key === 'client_name')?.places).toHaveLength(2);

    const without = withoutField(again, 'client_name');
    expect(labelText(without)).toContain('Для: ООО «Альфа»');
  });

  it('saves DOCX as a sample with places and PDF as a text template', () => {
    const docx = draftFromImport(imported);
    const request = sampleRequest(docx);
    expect(request).toMatchObject({ file_id: 9, body: '', kind: 'offer' });
    expect(request.fields[0]).toMatchObject({
      key: 'client_name',
      places: [{ text: 'ООО «Альфа»', before: '' }],
    });

    const pdf = draftFromImport({ ...imported, file_id: null, format: 'pdf' });
    const text = sampleRequest(pdf);
    expect(text.file_id).toBeUndefined();
    expect(text.body.split('\n')[1]).toBe('Для: {{client_name}}');
    expect(toTextDraft(pdf).text.split('\n')[1]).toBe('Для: {{Название клиента}}');
  });
});

describe('own template from a standard blank', () => {
  const blank = {
    text: 'Итого: {{total|rub}} руб.\n{{total|words}}\nПокупатель: {{client_name}}',
    fields: [
      { ...catalogField('total'), label: 'Стоимость', places: [] },
      { ...catalogField('client_name'), places: [] },
    ],
  };

  it('shows blank markers by field label and variant', () => {
    expect(labelText(blank)).toBe(
      'Итого: {{Стоимость, рубли}} руб.\n{{Стоимость, прописью}}\nПокупатель: {{Название клиента}}',
    );
  });

  it('knows which fields are marked in the blank itself', () => {
    expect(markedInFile(blank.text, 'total')).toBe(true);
    expect(markedInFile(blank.text, 'seller_name')).toBe(false);
  });
});

function catalogField(key: string) {
  const field = catalogByKey(key);
  if (!field) throw new Error(key);
  return field;
}
