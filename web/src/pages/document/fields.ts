// Состояние формы документа: что показать в полях, что изменилось и какие
// ошибки у каких полей. Чистые функции — их проверяют тесты без React.
import type { DocumentView, FieldSpec, FieldValue } from '@/api/client';
import { SOURCE_LABEL, documentName, toInputValue } from '@/lib/format';

export type Draft = Record<string, string>;

export function draftFromDocument(document: DocumentView): Draft {
  const draft: Draft = {};
  for (const field of document.template.fields) {
    const value = document.values[field.key];
    draft[field.key] = value ? toInputValue(field.type, value.value) : '';
  }
  return draft;
}

// Сервер пишет ««ИНН клиента»: ИНН не проходит проверку»; под самим полем
// название поля лишнее.
export function stripLabel(message: string): string {
  return message.replace(/^«[^»]+»:\s*/, '');
}

export function fieldErrors(document: DocumentView, showMissing: boolean): Record<string, string> {
  const errors: Record<string, string> = {};
  for (const error of document.errors) errors[error.key] = stripLabel(error.message);
  if (showMissing) {
    for (const key of document.missing) errors[key] ??= 'Заполните поле';
  }
  return errors;
}

export function changedValues(draft: Draft, initial: Draft): Draft {
  const changed: Draft = {};
  for (const [key, value] of Object.entries(draft)) {
    if (value.trim() !== (initial[key] ?? '').trim()) changed[key] = value;
  }
  return changed;
}

// После сохранения: принятые значения — в каноническом виде с сервера,
// отклонённые остаются как их ввёл человек, чтобы было что исправить.
export function mergeAfterSave(document: DocumentView, draft: Draft): Draft {
  const fresh = draftFromDocument(document);
  const rejected = new Set(document.errors.map((error) => error.key));
  const merged: Draft = { ...fresh };
  for (const key of rejected) {
    if (draft[key] !== undefined) merged[key] = draft[key];
  }
  return merged;
}

export function sourceOf(
  document: DocumentView,
  field: FieldSpec,
): { label: string; draft: boolean } | null {
  const value = document.values[field.key];
  if (!value || value.source === 'manual') return null;
  const draft = !value.confirmed && (value.source === 'ocr' || value.source === 'agent');
  return {
    label: draft ? `${SOURCE_LABEL[value.source]} · проверьте` : SOURCE_LABEL[value.source],
    draft,
  };
}

// Подпись документа под заголовком экрана: «Счёт на оплату № 17 · ООО «Альфа»».
// Вид шаблона — только если название своё, иначе он повторял бы название.
export function documentCaption(doc: DocumentView): string {
  const parts = [documentName(doc.title, doc.values['number']?.value)];
  if (doc.title !== doc.template.title) parts.push(doc.template.title);
  const client = doc.values['client_name']?.value;
  if (client) parts.push(client);
  return parts.join(' · ');
}

// Откуда прочитано значение, ждущее подтверждения: с фото — строка оригинала,
// от помощника — слова из сообщения.
export function fragmentLabel(source: FieldValue['source'], fragment: string): string {
  return source === 'agent' ? `В сообщении: «${fragment}»` : `На фото: «${fragment}»`;
}

export function labelsOf(document: DocumentView, keys: readonly string[]): string[] {
  const labels = new Map(document.template.fields.map((field) => [field.key, field.label]));
  return keys.map((key) => labels.get(key) ?? key);
}

// Текст к файлу по умолчанию, пока человек не написал свой или не попросил помощника.
// Название клиента сюда не подставляется: письмо читает сам клиент, а «для ООО
// Ромашка» без склонения («для Акционерное общество») читалось бы с ошибкой.
export function defaultCoverText(doc: DocumentView): string {
  const number = doc.values['number']?.value;
  const what = `${doc.template.title.toLowerCase()}${number ? ` № ${number}` : ''}`;
  return `Здравствуйте!\n\nНаправляю ${what}. Если появятся вопросы — напишите, обсудим.`;
}
