// Вкладка «Документы»: всё созданное — поиск, фильтр по виду и группы по клиентам.
// Группа клиента — то, что в макете называлось «проект»: документы одной
// сделки с одним контрагентом (отдельной сущности «проект» в API пока нет).
import { Button, CellHeader, CellList, CellSimple } from '@maxhub/max-ui';
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
import { matchesQuery, needsSearch } from '@/lib/search';
import { useScreenState } from '@/lib/screenMemory';
import { useAsync } from '@/lib/useAsync';

const NO_CLIENT = 'Без клиента';

function matches(doc: DocumentSummary, query: string): boolean {
  return matchesQuery(
    [doc.title, doc.number, doc.template_title, doc.client, doc.counterparty_name],
    query,
  );
}

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
  const [kind, setKind] = useScreenState<string | null>('kind', null);

  const [documents, templates] = state.data ?? [[], []];
  const kindByTitle = useMemo(
    () => new Map(templates.map((template) => [template.title, template.kind])),
    [templates],
  );
  const kinds = useMemo(
    () => [...new Set(documents.map((doc) => kindByTitle.get(doc.template_title) ?? 'other'))],
    [documents, kindByTitle],
  );

  const groups = useMemo(() => {
    const visible = documents
      .filter((doc) => !kind || (kindByTitle.get(doc.template_title) ?? 'other') === kind)
      .filter((doc) => matches(doc, query))
      .sort((a, b) => b.updated_at.localeCompare(a.updated_at));
    const byClient = new Map<string, DocumentSummary[]>();
    for (const doc of visible) {
      const client = doc.counterparty_name || doc.client || NO_CLIENT;
      byClient.set(client, [...(byClient.get(client) ?? []), doc]);
    }
    // Клиенты — по свежести последнего документа, «Без клиента» — в конце.
    return [...byClient.entries()].sort(([a], [b]) =>
      a === NO_CLIENT ? 1 : b === NO_CLIENT ? -1 : 0,
    );
  }, [documents, kind, kindByTitle, query]);

  return (
    <Page title="Мои документы" tabs>
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
          {/* Поиск и фильтр — когда документов столько, что их уже не окинуть взглядом. */}
          {needsSearch(documents.length) ? (
            <SearchField value={query} onChange={setQuery} hint="Название или клиент" />
          ) : null}
          {needsSearch(documents.length) && kinds.length > 1 ? (
            <FilterChips
              label="Вид документа"
              options={kinds.map((item) => ({ value: item, title: kindStyle(item).plural }))}
              value={kind}
              onChange={setKind}
            />
          ) : null}
          {groups.length === 0 ? <EmptyState title="Ничего не нашлось" /> : null}
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
