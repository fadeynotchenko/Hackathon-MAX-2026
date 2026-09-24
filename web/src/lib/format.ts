// Подписи и форматы для экранов. Хранение — каноническое (сумма «120000.00»,
// дата ISO), показ — по-русски; обратно в API уходит то, что ввёл человек,
// а приводит к канону сервер.
import type { DocumentSummary, FieldSpec, FieldType, ValueSource } from '@/api/client';

const DATE = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' });
const DATE_SHORT = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'short' });
const TIME = new Intl.DateTimeFormat('ru-RU', { hour: '2-digit', minute: '2-digit' });

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  return DATE.format(new Date(iso));
}

// «сегодня, 14:05», «вчера», «12 сент.» — для списков.
export function formatRelative(iso: string, now: Date = new Date()): string {
  const date = new Date(iso);
  const day = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const diffDays = Math.round((day(now) - day(date)) / 86_400_000);
  if (diffDays === 0) return `сегодня, ${TIME.format(date)}`;
  if (diffDays === 1) return 'вчера';
  if (date.getFullYear() === now.getFullYear()) return DATE_SHORT.format(date);
  return DATE.format(date);
}

export function formatDateTime(iso: string): string {
  const date = new Date(iso);
  return `${DATE_SHORT.format(date)}, ${TIME.format(date)}`;
}

export function formatMoney(raw: string): string {
  const amount = Number(raw);
  if (!Number.isFinite(amount)) return raw;
  // Пробел между разрядами — обычный, как в документе: неразрывный из Intl
  // выглядел бы так же, но ломал бы сравнение «человек поменял значение».
  return amount
    .toLocaleString('ru-RU', {
      minimumFractionDigits: Number.isInteger(amount) ? 0 : 2,
      maximumFractionDigits: 2,
    })
    .replace(/\s/g, ' ');
}

// Значение из API → строка для показа: сумма и дата по-русски.
export function displayValue(type: FieldType, raw: string): string {
  if (type === 'date') {
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(raw);
    return match ? `${match[3]}.${match[2]}.${match[1]}` : raw;
  }
  return toInputValue(type, raw);
}

// Значение из API → строка для поля ввода (дата остаётся ISO для <input type="date">).
export function toInputValue(type: FieldType, raw: string): string {
  if (type === 'money') return formatMoney(raw);
  return raw;
}

export interface InputKind {
  type: 'text' | 'email' | 'tel' | 'date';
  inputMode?: 'text' | 'numeric' | 'decimal' | 'email' | 'tel';
  multiline?: boolean;
  suffix?: string;
}

export function inputKind(type: FieldType): InputKind {
  switch (type) {
    case 'multiline':
      return { type: 'text', multiline: true };
    case 'email':
      return { type: 'email', inputMode: 'email' };
    case 'phone':
      return { type: 'tel', inputMode: 'tel' };
    case 'date':
      return { type: 'date' };
    case 'money':
      return { type: 'text', inputMode: 'decimal', suffix: '₽' };
    case 'integer':
    case 'inn':
    case 'kpp':
    case 'ogrn':
    case 'bic':
    case 'account':
      return { type: 'text', inputMode: 'numeric' };
    default:
      return { type: 'text' };
  }
}

export const SOURCE_LABEL: Record<ValueSource, string> = {
  manual: 'Вручную',
  profile: 'Из профиля',
  counterparty: 'Из карточки клиента',
  ocr: 'С фото',
  agent: 'От помощника',
};

// Группы полей шаблона → разделы формы. Порядок — как в сценарии: кому,
// что и на каких условиях, затем свои реквизиты (обычно уже из профиля).
export const GROUP_ORDER = ['Клиент', 'Предмет', 'Продавец'] as const;
export const GROUP_TITLE: Record<string, string> = {
  Клиент: 'Клиент',
  Предмет: 'Условия',
  Продавец: 'Ваша организация',
};

export function groupFields(fields: FieldSpec[]): Array<[string, FieldSpec[]]> {
  const groups = new Map<string, FieldSpec[]>();
  for (const field of fields) {
    const list = groups.get(field.group) ?? [];
    list.push(field);
    groups.set(field.group, list);
  }
  const rank = (group: string) => {
    const index = (GROUP_ORDER as readonly string[]).indexOf(group);
    return index === -1 ? GROUP_ORDER.length : index;
  };
  return [...groups.entries()].sort(([a], [b]) => rank(a) - rank(b));
}

// Вид документа → короткое имя, метка и цвет аватара в списках.
export interface KindStyle {
  short: string;
  plural: string;
  gradient: 'green' | 'blue' | 'purple' | 'orange';
}

export const KIND_STYLE: Record<string, KindStyle> = {
  invoice: { short: 'СЧ', plural: 'Счета', gradient: 'green' },
  offer: { short: 'КП', plural: 'КП', gradient: 'blue' },
  contract: { short: 'ДГ', plural: 'Договоры', gradient: 'purple' },
};

export function kindStyle(kind: string | undefined): KindStyle {
  return (kind && KIND_STYLE[kind]) || { short: 'ДК', plural: 'Другие', gradient: 'orange' };
}

// Состояние документа одной строкой: черновик → готов → отправлен → в чате.
export function documentState(doc: Pick<DocumentSummary, 'status' | 'sent'>): {
  label: string;
  tone: 'draft' | 'ready' | 'sent' | 'failed';
} {
  if (doc.sent) {
    const format = doc.sent.format ? ` ${doc.sent.format.toUpperCase()}` : '';
    if (doc.sent.delivery === 'delivered') return { label: `В чате${format}`, tone: 'sent' };
    if (doc.sent.delivery === 'failed') return { label: 'Не доставлен', tone: 'failed' };
    return { label: `Отправляется${format}`, tone: 'sent' };
  }
  if (doc.status === 'ready') return { label: 'Готов', tone: 'ready' };
  return { label: 'Черновик', tone: 'draft' };
}

export const FACT_LABEL: Record<string, string> = {
  created: 'Создан',
  ready: 'Все поля заполнены',
  rendered: 'Файл собран',
  sent: 'Отправлен в чат',
  delivered: 'Доставлен в чат',
  delivery_failed: 'Не доставлен',
  rejected: 'Значение не прошло проверку',
};

export function pluralize(count: number, one: string, few: string, many: string): string {
  const mod10 = count % 10;
  const mod100 = count % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;
  return many;
}

// Буквы для аватара организации: без организационно-правовой формы.
export function initials(name: string): string {
  const words = name
    .replace(/[«»"']/g, '')
    .split(/\s+/)
    .filter((word) => word && !/^(ООО|АО|ПАО|ЗАО|ИП|ОАО)$/i.test(word));
  return (
    words
      .slice(0, 2)
      .map((word) => word[0]?.toUpperCase())
      .join('') || '?'
  );
}
