// Реквизиты стороны — одни и те же для своей организации и для клиента
// (core.usecases.documents.requisites). Разделы — как в макете профиля:
// юрданные, банк и подписант, контакты.
import type { FieldType } from '@/api/client';

export interface RequisiteSpec {
  key: string;
  label: string;
  type: FieldType;
  // Пример значения — подсказкой под полем.
  example?: string;
}

export const REQUISITE_GROUPS: Array<{ title: string; fields: RequisiteSpec[] }> = [
  {
    title: 'Юрданные',
    fields: [
      { key: 'name', label: 'Название', type: 'text', example: 'ООО «Ромашка»' },
      { key: 'inn', label: 'ИНН', type: 'inn' },
      { key: 'kpp', label: 'КПП', type: 'kpp' },
      { key: 'ogrn', label: 'ОГРН или ОГРНИП', type: 'ogrn' },
      { key: 'address', label: 'Юридический адрес', type: 'address' },
    ],
  },
  {
    title: 'Банк и подписант',
    fields: [
      { key: 'bank', label: 'Банк', type: 'text', example: 'ПАО Сбербанк' },
      { key: 'bic', label: 'БИК', type: 'bic' },
      { key: 'account', label: 'Расчётный счёт', type: 'account' },
      { key: 'director', label: 'Подписант', type: 'name', example: 'Иванов Иван Иванович' },
    ],
  },
  {
    title: 'Контакты',
    fields: [
      { key: 'phone', label: 'Телефон', type: 'phone', example: '+7 900 000-00-00' },
      { key: 'email', label: 'Почта', type: 'email', example: 'mail@company.ru' },
    ],
  },
];

export type Requisites = Record<string, string>;

// Сервер склеивает ошибки реквизитов в одну строку через «; »: разносим их по
// полям по названию в кавычках, нераспознанное остаётся общей ошибкой.
export function splitRequisiteErrors(message: string): {
  byField: Record<string, string>;
  rest: string[];
} {
  const labelToKey = new Map<string, string>([
    ['Название', 'name'],
    ['ИНН', 'inn'],
    ['КПП', 'kpp'],
    ['ОГРН', 'ogrn'],
    ['Адрес', 'address'],
    ['Подписант', 'director'],
    ['Банк', 'bank'],
    ['БИК', 'bic'],
    ['Расчётный счёт', 'account'],
    ['Телефон', 'phone'],
    ['Почта', 'email'],
  ]);
  const byField: Record<string, string> = {};
  const rest: string[] = [];
  for (const part of message.split(/;\s*/).filter(Boolean)) {
    const match = /^«([^»]+)»:\s*(.+)$/.exec(part);
    const key = match ? labelToKey.get(match[1] ?? '') : undefined;
    if (key && match?.[2]) byField[key] = match[2];
    else rest.push(part);
  }
  return { byField, rest };
}
