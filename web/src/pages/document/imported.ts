// Что сказать над формой документа, сделанного по своему файлу.
import type { DocumentImport } from '@/api/client';
import { pluralize } from '@/lib/format';

export interface ImportNotice {
  tone: 'success' | 'info';
  title: string;
  text: string;
}

const FOUND_BY: Record<DocumentImport['found_by'], string> = {
  markers: 'по меткам в файле',
  assistant: 'помощником',
  rules: 'по линейкам и реквизитам',
};

export function importNotice(result: DocumentImport): ImportNotice {
  const count = result.document.template.fields.length;
  const places = `${count} ${pluralize(count, 'место', 'места', 'мест')} для данных`;
  const title = `Нашли ${places} ${FOUND_BY[result.found_by]}`;
  const text =
    result.notice ??
    'Значения — как в файле. Поменяйте нужные: файл соберётся в том же оформлении.';
  return { tone: result.format === 'pdf' ? 'info' : 'success', title, text };
}
