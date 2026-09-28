// Отбор и группы «Моих документов»: поиск, статус, вид и порядок — по клиентам
// (документы одной сделки рядом) или просто по дате, когда ищут «тот, вчерашний».
import type { DocumentSummary } from '@/api/client';
import { documentState } from '@/lib/format';
import { matchesQuery } from '@/lib/search';

export const NO_CLIENT = 'Без клиента';

export type StatusFilter = 'draft' | 'ready' | 'sent';
export type Grouping = 'client' | 'date';

export const STATUS_FILTERS: ReadonlyArray<{ value: StatusFilter; title: string }> = [
  { value: 'draft', title: 'Черновики' },
  { value: 'ready', title: 'Готовы' },
  { value: 'sent', title: 'Отправлены' },
];

export interface ArchiveFilter {
  query: string;
  status: StatusFilter | null;
  kind: string | null;
  kindOf: (doc: DocumentSummary) => string;
}

function statusOf(doc: DocumentSummary): StatusFilter {
  const tone = documentState(doc).tone;
  // Не дошедший до чата — тоже отправленный: его ищут среди отправленных.
  return tone === 'failed' ? 'sent' : tone;
}

export function filterDocuments(
  documents: DocumentSummary[],
  { query, status, kind, kindOf }: ArchiveFilter,
): DocumentSummary[] {
  return documents
    .filter((doc) => !status || statusOf(doc) === status)
    .filter((doc) => !kind || kindOf(doc) === kind)
    .filter((doc) =>
      matchesQuery(
        [doc.title, doc.number, doc.template_title, doc.client, doc.counterparty_name],
        query,
      ),
    )
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at));
}

// Документы уже по свежести: группа клиента встаёт по его последнему документу,
// группа даты — «Сегодня», «Вчера», «На этой неделе», дальше по месяцам.
export function groupDocuments(
  documents: DocumentSummary[],
  grouping: Grouping,
  now: Date = new Date(),
): Array<[string, DocumentSummary[]]> {
  const groups = new Map<string, DocumentSummary[]>();
  for (const doc of documents) {
    const title =
      grouping === 'client'
        ? doc.counterparty_name || doc.client || NO_CLIENT
        : dayTitle(doc.updated_at, now);
    groups.set(title, [...(groups.get(title) ?? []), doc]);
  }
  const entries = [...groups.entries()];
  if (grouping === 'client') {
    // «Без клиента» — в конце, остальные — в порядке свежести.
    entries.sort(([a], [b]) => (a === NO_CLIENT ? 1 : b === NO_CLIENT ? -1 : 0));
  }
  return entries;
}

function dayTitle(iso: string, now: Date): string {
  const day = new Date(iso);
  const start = (date: Date) => new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const days = Math.round((start(now).getTime() - start(day).getTime()) / 86_400_000);
  if (days <= 0) return 'Сегодня';
  if (days === 1) return 'Вчера';
  if (days < 7) return 'На этой неделе';
  return day.toLocaleDateString('ru-RU', { month: 'long', year: 'numeric' });
}
