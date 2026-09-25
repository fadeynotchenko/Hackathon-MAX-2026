// Метрики админки: ответ /admin/metrics → ряды для графиков и итоги периода.
// Чистые функции без React: экран только рисует то, что посчитано здесь.
import type { AdminMetrics, DailyMetrics, ValueSource } from '@/api/client';
import { FACT_LABEL, kindStyle, SOURCE_LABEL } from '@/lib/format';

export const PERIODS = [
  { days: 7, label: '7 дней' },
  { days: 30, label: '30 дней' },
  { days: 90, label: '90 дней' },
  { days: 180, label: 'Полгода' },
] as const;

export const DEFAULT_PERIOD = 30;

// Дольше двух месяцев столбик на день выходит тоньше пикселя на экране телефона:
// столбчатые ряды тогда считаются по неделям. Линии остаются по дням.
export const WEEKLY_AFTER_DAYS = 60;

const PERCENT = new Intl.NumberFormat('ru-RU', { style: 'percent', maximumFractionDigits: 0 });
const DECIMAL = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 1 });
// День в ответе — календарная дата по Москве без времени: форматируем в UTC,
// чтобы часовой пояс телефона не сдвинул её на соседний день.
const DAY = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'short', timeZone: 'UTC' });
const DAY_WITH_YEAR = new Intl.DateTimeFormat('ru-RU', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  timeZone: 'UTC',
});

function parseDay(iso: string): Date {
  const [year = 1970, month = 1, day = 1] = iso.split('-').map(Number);
  return new Date(Date.UTC(year, month - 1, day));
}

export function formatShare(share: number | null | undefined): string {
  return share === null || share === undefined ? '—' : PERCENT.format(share);
}

export function formatDay(iso: string): string {
  return DAY.format(parseDay(iso));
}

// «18–24 сент.», через границу месяца — «28 авг. – 3 сент.».
export function formatRange(fromIso: string, toIso: string): string {
  if (fromIso === toIso) return formatDay(fromIso);
  const from = parseDay(fromIso);
  const to = parseDay(toIso);
  if (from.getUTCMonth() === to.getUTCMonth() && from.getUTCFullYear() === to.getUTCFullYear()) {
    return `${from.getUTCDate()}–${DAY.format(to)}`;
  }
  return `${DAY.format(from)} – ${DAY.format(to)}`;
}

export function formatPeriod(sinceIso: string, untilIso: string): string {
  return `${DAY.format(parseDay(sinceIso))} – ${DAY_WITH_YEAR.format(parseDay(untilIso))}`;
}

// Число и единица не разрываются переносом строки: «2,9 с», а не «2,9» и «с».
const NBSP = '\u00a0';

// Время до отправки: «меньше минуты», «12 мин», «2 ч 5 мин», «3 дн 4 ч».
export function formatMinutes(minutes: number | null | undefined): string {
  if (minutes === null || minutes === undefined) return '—';
  if (minutes < 1) return 'меньше минуты';
  const total = Math.round(minutes);
  if (total < 60) return `${total}${NBSP}мин`;
  const hours = Math.floor(total / 60);
  if (hours < 24) {
    const rest = total % 60;
    return rest ? `${hours}${NBSP}ч ${rest}${NBSP}мин` : `${hours}${NBSP}ч`;
  }
  const days = Math.floor(hours / 24);
  const restHours = hours % 24;
  return restHours ? `${days}${NBSP}дн ${restHours}${NBSP}ч` : `${days}${NBSP}дн`;
}

// Время сборки файла: «850 мс», «1,8 с».
export function formatMs(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return '—';
  if (ms < 1000) return `${Math.round(ms)}${NBSP}мс`;
  return `${DECIMAL.format(ms / 1000)}${NBSP}с`;
}

export interface Bucket {
  key: string;
  label: string;
  days: DailyMetrics[];
}

export interface Buckets {
  weekly: boolean;
  items: Bucket[];
}

// Дни → столбцы. Недели считаются от последнего дня: последний столбец —
// полная неделя по сегодня, неполной может быть только первая.
export function toBuckets(daily: DailyMetrics[]): Buckets {
  const weekly = daily.length > WEEKLY_AFTER_DAYS;
  if (!weekly) {
    return {
      weekly,
      items: daily.map((day) => ({ key: day.day, label: formatDay(day.day), days: [day] })),
    };
  }
  const items: Bucket[] = [];
  for (let end = daily.length; end > 0; end -= 7) {
    const days = daily.slice(Math.max(0, end - 7), end);
    const first = days[0];
    const last = days[days.length - 1];
    if (!first || !last) continue;
    items.unshift({ key: first.day, label: formatRange(first.day, last.day), days });
  }
  return { weekly, items };
}

export function sumOf(days: DailyMetrics[], pick: (day: DailyMetrics) => number): number {
  return days.reduce((total, day) => total + pick(day), 0);
}

export interface Row {
  key: string;
  label: string;
  value: number;
  // Доля от базы строки (воронка — от созданных, автозаполнение — от всех полей).
  share?: number | null;
  // Контекст, а не главное (ручной ввод рядом с автозаполнением): серым.
  muted?: boolean;
}

const byValue = (a: Row, b: Row) => b.value - a.value;

export function kindsTotal(daily: DailyMetrics[]): Row[] {
  const counts = new Map<string, number>();
  for (const day of daily) {
    for (const [kind, count] of Object.entries(day.created_by_kind)) {
      counts.set(kind, (counts.get(kind) ?? 0) + count);
    }
  }
  return [...counts.entries()]
    .map(([kind, value]) => ({ key: kind, label: kindStyle(kind).plural, value }))
    .sort(byValue);
}

export function formatsTotal(daily: DailyMetrics[]): Row[] {
  return [
    { key: 'pdf', label: 'PDF', value: sumOf(daily, (day) => day.rendered_pdf) },
    { key: 'docx', label: 'DOCX', value: sumOf(daily, (day) => day.rendered_docx) },
  ].sort(byValue);
}

const FUNNEL_STAGES = ['created', 'ready', 'rendered', 'sent', 'delivered'] as const;

// Документы периода по шагам; доля — от созданных, чтобы видеть, где теряются.
export function funnelRows(funnel: AdminMetrics['funnel']): Row[] {
  return FUNNEL_STAGES.map((stage) => ({
    key: stage,
    label: FACT_LABEL[stage] ?? stage,
    value: funnel[stage],
    share: funnel.created ? funnel[stage] / funnel.created : null,
  }));
}

// Поля документов по источнику. Ручной ввод — контекст: главное — сколько
// полей продукт заполнил сам.
export function autofillRows(autofill: AdminMetrics['autofill']): Row[] {
  return Object.entries(autofill.by_source)
    .filter(([, value]) => value > 0)
    .map(([source, value]) => ({
      key: source,
      label: SOURCE_LABEL[source as ValueSource] ?? source,
      value,
      share: autofill.total ? value / autofill.total : null,
      muted: source === 'manual',
    }))
    .sort(byValue);
}

export const REJECTION_LABEL: Record<string, string> = {
  'field.inn_invalid': 'ИНН не прошёл проверку',
  'field.kpp_invalid': 'Неверный КПП',
  'field.ogrn_invalid': 'ОГРН не прошёл проверку',
  'field.bic_invalid': 'Неверный БИК',
  'field.account_invalid': 'Неверный расчётный счёт',
  'field.account_key_invalid': 'Счёт не сходится с БИК',
  'field.money_invalid': 'Сумма не распознана',
  'field.date_invalid': 'Неверная дата',
  'field.integer_invalid': 'Не целое число',
  'field.email_invalid': 'Неверная почта',
  'field.phone_invalid': 'Неверный телефон',
  'field.too_long': 'Слишком длинное значение',
  'field.control_chars': 'Служебные символы',
  'field.unknown': 'Неизвестное поле',
  unknown: 'Без кода',
};

export function rejectionRows(rejections: AdminMetrics['rejections']): Row[] {
  return Object.entries(rejections)
    .map(([code, value]) => ({ key: code, label: REJECTION_LABEL[code] ?? code, value }))
    .sort(byValue);
}

export interface Summary {
  usersTotal: number;
  usersNew: number;
  activeWeek: number;
  activeToday: number;
  documentsCreated: number;
  documentsCopied: number;
  automaticShare: number | null;
}

export function summarize(metrics: AdminMetrics): Summary {
  const last = metrics.daily[metrics.daily.length - 1];
  return {
    usersTotal: last?.users_total ?? 0,
    usersNew: sumOf(metrics.daily, (day) => day.users_new),
    activeWeek: last?.active_week ?? 0,
    activeToday: last?.active_day ?? 0,
    documentsCreated: sumOf(metrics.daily, (day) => day.documents_created),
    documentsCopied: sumOf(metrics.daily, (day) => day.documents_copied),
    automaticShare: metrics.autofill.automatic_share,
  };
}
