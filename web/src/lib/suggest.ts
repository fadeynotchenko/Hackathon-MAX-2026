// Подсказки из реестров (ручка /suggest, за ней DaData): какое поле что ищет
// и какие поля заполняет выбранная подсказка. Чистые функции — их проверяют
// тесты без React.
//
// Организация ищется по названию или ИНН и заполняет все реквизиты стороны,
// банк — по названию или БИК и заполняет БИК и корр. счёт, адрес — только сам
// себя. В документе реквизиты стороны живут с префиксом (client_inn,
// seller_bank), в карточке — без него: подсказка приходит с короткими ключами,
// префикс добавляет форма.
import type { FieldType, RequisiteSuggestion } from '@/api/client';

export type SuggestKind = 'company' | 'bank' | 'address';

// Префиксы сторон в ключах полей документа (core.usecases.documents.requisites).
export const SIDE_PREFIXES = ['seller_', 'client_'] as const;

// Подпись над списком подсказок: откуда эти строки.
export const SUGGEST_TITLE: Record<SuggestKind, string> = {
  company: 'Организации и ИП из ЕГРЮЛ',
  bank: 'Банки по справочнику БИК',
  address: 'Адреса по ФИАС',
};

// Метка у поля, заполненного из подсказки: значение реестра сверять не нужно.
export const REGISTRY_SOURCE = { label: 'Из реестра', draft: false } as const;

// Короче реестр отвечает случайными совпадениями, а каждый запрос тратит
// дневной лимит ключа.
export const MIN_SUGGEST_QUERY = 3;

const COMPANY_KEYS = new Set(['name', 'inn']);
const BANK_KEYS = new Set(['bank', 'bic']);

export interface SuggestTarget {
  kind: SuggestKind;
  prefix: string;
}

export function suggestTarget(
  key: string,
  type: FieldType,
  prefixes: readonly string[],
): SuggestTarget | null {
  for (const prefix of prefixes) {
    if (!key.startsWith(prefix)) continue;
    const base = key.slice(prefix.length);
    if (COMPANY_KEYS.has(base)) return { kind: 'company', prefix };
    if (BANK_KEYS.has(base)) return { kind: 'bank', prefix };
  }
  return type === 'address' ? { kind: 'address', prefix: '' } : null;
}

// Что подставить по выбранной подсказке: адрес — в то поле, где его искали,
// остальное — в поля стороны, которые есть в форме. keys === null — форма
// принимает любые ключи (карточка реквизитов).
export function suggestionValues(
  target: SuggestTarget,
  fieldKey: string,
  suggestion: RequisiteSuggestion,
  keys: ReadonlySet<string> | null,
): Record<string, string> {
  if (target.kind === 'address') {
    const address = suggestion.values['address'];
    return address ? { [fieldKey]: address } : {};
  }
  const values: Record<string, string> = {};
  for (const [key, value] of Object.entries(suggestion.values)) {
    const full = `${target.prefix}${key}`;
    if (value && (keys === null || keys.has(full))) values[full] = value;
  }
  return values;
}

// Без ключа DaData ручка отвечает 503 — дальше в этой вкладке не спрашиваем,
// поле работает как обычное.
let unavailable = false;

export function suggestUnavailable(): boolean {
  return unavailable;
}

export function markSuggestUnavailable(): void {
  unavailable = true;
}
