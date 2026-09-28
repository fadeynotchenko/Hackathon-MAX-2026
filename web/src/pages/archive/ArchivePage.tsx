// Вкладка «Документы»: всё созданное — поиск, фильтры по статусу и виду,
// группы по клиентам или по дате.
// Группа клиента — то, что в макете называлось «проект»: документы одной
// сделки с одним контрагентом (отдельной сущности «проект» в API пока нет).
import { Button, CellHeader, CellList, CellSimple, Typography } from '@maxhub/max-ui';
import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';

import type { DocumentSummary } from '@/api/client';
import { FilterChips } from '@/components/FilterChips';
import { Page } from '@/components/Page';
import { SearchField } from '@/components/SearchField';
import { EmptyState, ErrorState, Loading } from '@/components/StateViews';
import { useAuth } from '@/auth/context';
import {
  type DocumentState,
  documentName,
  documentState,
  formatRelative,
  kindStyle,
} from '@/lib/format';
import { useScreenState } from '@/lib/screenMemory';
import { useAsync } from '@/lib/useAsync';

import {
  filterDocuments,
  type Grouping,
  groupDocuments,
  STATUS_FILTERS,
  type StatusFilter,
} from './archive';

const STATUS_TONE: Record<DocumentState['tone'], string> = {
  draft: '',
  ready: 'themed',
  sent: 'themed',
  failed: 'negative',
};

export function ArchivePage() {
  const { api } = useAuth();
  const navigate = useNavigate();
  const state = useAsync(() => Promise.all([api.documents(), api.templates()]), [api]);
  const [query, setQuery] = useScreenState('query', '');
  // Один ряд фильтров: статус или вид документа — «status:draft», «kind:offer».
  const [filter, setFilter] = useScreenState<string | null>('filter', null);
  const [scope, value] = filter?.split(':') ?? [];
  const status = scope === 'status' ? (value as StatusFilter) : null;
  const kind = scope === 'kind' ? (value ?? null) : null;
  const [grouping, setGrouping] = useScreenState<Grouping>('grouping', 'client');

  const [documents, templates] = state.data ?? [[], []];
  const kindByTitle = useMemo(
    () => new Map(templates.map((template) => [template.title, template.kind])),
    [templates],
  );
  const kindOf = useMemo(
    () => (doc: DocumentSummary) => kindByTitle.get(doc.template_title) ?? 'other',
    [kindByTitle],
  );
  const kinds = useMemo(() => [...new Set(documents.map(kindOf))], [documents, kindOf]);
  const visible = useMemo(
    () => filterDocuments(documents, { query, status, kind, kindOf }),
    [documents, query, status, kind, kindOf],
  );
  const groups = useMemo(() => groupDocuments(visible, grouping), [visible, grouping]);
  const filtered = Boolean(query.trim() || status || kind);

  return (
    <Page
      title="Мои документы"
      tabs
      headerAfter={
        documents.length > 1 ? (
          // Порядок — в шапке, а не отдельной строкой над списком: переключают
          // его редко, а место под поиском нужнее фильтрам.
          <Button
            size="small"
            variant="secondary"
            aria-label={`Порядок: ${grouping === 'client' ? 'по клиентам' : 'по дате'}`}
            onClick={() => setGrouping(grouping === 'client' ? 'date' : 'client')}
          >
            {grouping === 'client' ? 'По клиентам' : 'По дате'}
          </Button>
        ) : null
      }
    >
      {state.loading ? <Loading /> : null}
      {state.error ? <ErrorState message={state.error} onRetry={state.reload} /> : null}
      {state.data && documents.length === 0 ? (
        <EmptyState
          title="Документов пока нет"
          action={<Button onClick={() => navigate('/create')}>Создать документ</Button>}
        />
      ) : null}
      {state.data && documents.length > 0 ? (
        <>
          {/* Поиск и фильтры — всегда: даже десяток документов быстрее найти
              по клиенту или статусу, чем пролистать. */}
          <SearchField value={query} onChange={setQuery} hint="Название, номер или клиент" />
          <FilterChips
            label="Фильтр"
            options={[
              ...STATUS_FILTERS.map((item) => ({
                value: `status:${item.value}`,
                title: item.title,
              })),
              ...(kinds.length > 1
                ? kinds.map((item) => ({ value: `kind:${item}`, title: kindStyle(item).plural }))
                : []),
            ]}
            value={filter}
            onChange={setFilter}
          />
          {filtered && visible.length > 0 ? (
            <Typography.Text variant="description" color="tertiary" className="archive__found">
              Нашлось {visible.length} из {documents.length}
            </Typography.Text>
          ) : null}
          {groups.length === 0 ? (
            <EmptyState
              title="Ничего не нашлось"
              action={
                <Button
                  variant="secondary"
                  onClick={() => {
                    setQuery('');
                    setFilter(null);
                  }}
                >
                  Сбросить фильтры
                </Button>
              }
            />
          ) : null}
          {groups.map(([client, docs]) => (
            <CellList
              key={client}
              mode="island"
              filled
              header={<CellHeader innerClassNames={{ content: 'clamp-2' }}>{client}</CellHeader>}
            >
              {docs.map((doc) => {
                const status = documentState(doc);
                return (
                  <CellSimple
                    key={doc.id}
                    title={documentName(doc.title, doc.number)}
                    // Статус — первым словом подписи: так строка не переносится
                    // и название видно целиком.
                    subtitle={
                      <>
                        <span className={STATUS_TONE[status.tone]}>{status.label}</span>
                        {` · ${formatRelative(doc.updated_at)}`}
                      </>
                    }
                    innerClassNames={{ title: 'ellipsis', subtitle: 'ellipsis' }}
                    showChevron
                    onClick={() => navigate(`/documents/${doc.id}`)}
                  />
                );
              })}
            </CellList>
          ))}
        </>
      ) : null}
    </Page>
  );
}
