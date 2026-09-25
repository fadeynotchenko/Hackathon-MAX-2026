// Вкладка «Архив»: всё созданное — поиск, фильтр по виду и группы по клиентам.
// Группа клиента — то, что в макете называлось «проект»: документы одной
// сделки с одним контрагентом (отдельной сущности «проект» в API пока нет).
import { Button, CellHeader, CellList, CellSimple, Typography } from '@maxhub/max-ui';
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import type { DocumentSummary } from '@/api/client';
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
  pluralize,
} from '@/lib/format';
import { matchesQuery } from '@/lib/search';
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
  const [query, setQuery] = useState('');
  const [kind, setKind] = useState<string | null>(null);

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
    <Page title="Архив" subtitle="Документы, которые вы создали" tabs>
      {state.loading ? <Loading /> : null}
      {state.error ? <ErrorState message={state.error} onRetry={state.reload} /> : null}
      {state.data && documents.length === 0 ? (
        <EmptyState
          title="Документов пока нет"
          text="Созданные документы и их отправки появятся здесь."
          action={<Button onClick={() => navigate('/create')}>Создать документ</Button>}
        />
      ) : null}
      {state.data && documents.length > 0 ? (
        <>
          <SearchField value={query} onChange={setQuery} hint="Название, вид или клиент" />
          {kinds.length > 1 ? (
            <div className="chips" role="group" aria-label="Вид документа">
              <Button
                size="small"
                variant={kind === null ? 'primary' : 'secondary'}
                onClick={() => setKind(null)}
              >
                Все
              </Button>
              {kinds.map((item) => (
                <Button
                  key={item}
                  size="small"
                  variant={kind === item ? 'primary' : 'secondary'}
                  onClick={() => setKind(kind === item ? null : item)}
                >
                  {kindStyle(item).plural}
                </Button>
              ))}
            </div>
          ) : null}
          {groups.length === 0 ? (
            <EmptyState
              title="Ничего не нашлось"
              text="Попробуйте другое слово или сбросьте фильтр."
            />
          ) : null}
          {groups.map(([client, docs]) => (
            <CellList
              key={client}
              mode="island"
              filled
              header={
                <CellHeader
                  innerClassNames={{ content: 'clamp-2' }}
                  after={
                    <Typography.Text variant="description" color="tertiary">
                      {docs.length} {pluralize(docs.length, 'документ', 'документа', 'документов')}
                    </Typography.Text>
                  }
                >
                  {client}
                </CellHeader>
              }
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
