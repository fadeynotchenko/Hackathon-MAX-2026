// Вкладка «Архив»: всё созданное — поиск, фильтр по виду и группы по клиентам.
// Группа клиента — то, что в макете называлось «проект»: документы одной
// сделки с одним контрагентом (отдельной сущности «проект» в API пока нет).
import {
  Avatar,
  Button,
  CellHeader,
  CellList,
  CellSimple,
  Icon16SearchOutline,
  Input,
  Typography,
} from '@maxhub/max-ui';
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import type { DocumentSummary } from '@/api/client';
import { Page } from '@/components/Page';
import { EmptyState, ErrorState, Loading } from '@/components/StateViews';
import { useAuth } from '@/auth/context';
import { documentState, formatRelative, kindStyle, pluralize } from '@/lib/format';
import { useAsync } from '@/lib/useAsync';

const NO_CLIENT = 'Без клиента';

function matches(doc: DocumentSummary, query: string): boolean {
  if (!query) return true;
  const haystack = [doc.title, doc.template_title, doc.client, doc.counterparty_name]
    .filter(Boolean)
    .join(' ')
    .toLowerCase();
  return query
    .toLowerCase()
    .split(/\s+/)
    .every((word) => haystack.includes(word));
}

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
      .filter((doc) => matches(doc, query.trim()))
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
          <div className="section">
            <Input
              type="search"
              aria-label="Поиск по названию или клиенту"
              placeholder="Название, вид или клиент"
              mode="contrast"
              iconBefore={<Icon16SearchOutline />}
              withClearButton
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </div>
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
                const style = kindStyle(kindByTitle.get(doc.template_title));
                const status = documentState(doc);
                return (
                  <CellSimple
                    key={doc.id}
                    title={doc.title}
                    subtitle={`${doc.template_title} · ${formatRelative(doc.updated_at)}`}
                    before={
                      <Avatar.Container size={40} form="squircle">
                        <Avatar.Text gradient={style.gradient}>{style.short}</Avatar.Text>
                      </Avatar.Container>
                    }
                    after={
                      <Typography.Text
                        variant="description"
                        className={`nowrap ${status.tone === 'failed' ? 'negative' : status.tone === 'draft' ? 'faint' : 'themed'}`}
                      >
                        {status.label}
                      </Typography.Text>
                    }
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
