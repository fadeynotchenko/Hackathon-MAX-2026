// Вкладка «Создать»: каталог шаблонов — единственная точка выбора бланка
// (в макете каталог жил и здесь, и в профиле). Когда у пользователя есть свои
// шаблоны, каталог делится по видам документа: свой КП стоит рядом со
// стандартным, как «Шаблоны КП» в макете. Отсюда же создаётся новый свой
// шаблон. Второй вход — чат с ботом.
import { CellHeader, CellList, CellSimple, Typography } from '@maxhub/max-ui';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import type { Template } from '@/api/client';
import { Banner } from '@/components/Banner';
import { IconChat, IconPlus, IconUpload } from '@/components/icons';
import { Page, Section } from '@/components/Page';
import { SearchField } from '@/components/SearchField';
import { EmptyState, ErrorState, Loading } from '@/components/StateViews';
import { DocPreview } from '@/components/DocPreview';
import { useAuth } from '@/auth/context';
import { kindStyle } from '@/lib/format';
import { matchesQuery, needsSearch } from '@/lib/search';
import { useAsync } from '@/lib/useAsync';
import { closeApp, haptic } from '@/max/webapp';

import { catalogSections } from './catalog';

export function CreatePage() {
  const { api } = useAuth();
  const navigate = useNavigate();
  const templates = useAsync(() => api.templates(), [api]);
  const [chatHint, setChatHint] = useState(false);
  const [query, setQuery] = useState('');
  const all = templates.data ?? [];
  const visible = all.filter((template) =>
    matchesQuery(
      [
        template.title,
        template.description,
        kindStyle(template.kind).short,
        kindStyle(template.kind).section,
      ],
      query,
    ),
  );
  // Заголовок «Шаблоны» над единственной сеткой ничего не различает — разделы
  // подписаны, только когда каталог делится по видам.
  const grouped = all.some((template) => !template.is_builtin);

  const open = (template: Template) => {
    haptic('light');
    void navigate(`/create/${template.id}`);
  };

  const toChat = () => {
    if (!closeApp()) setChatHint(true);
  };

  return (
    <Page title="Новый документ" tabs>
      {templates.loading ? <Loading /> : null}
      {templates.error ? <ErrorState message={templates.error} onRetry={templates.reload} /> : null}
      {needsSearch(all.length) ? (
        <SearchField value={query} onChange={setQuery} hint="Счёт, договор, КП" />
      ) : null}
      {all.length > 0 && visible.length === 0 ? <EmptyState title="Ничего не нашлось" /> : null}
      {catalogSections(visible).map(([title, list]) => (
        <Section key={title} title={grouped ? title : undefined}>
          <TemplateGrid templates={list} onOpen={open} />
        </Section>
      ))}

      <CellList mode="island" filled header={<CellHeader>Свой шаблон</CellHeader>}>
        <CellSimple
          title="Из файла"
          subtitle="DOCX или PDF"
          before={
            <span className="themed-icon">
              <IconUpload />
            </span>
          }
          showChevron
          onClick={() => navigate('/templates/upload')}
        />
        <CellSimple
          title="Написать текст"
          before={
            <span className="themed-icon">
              <IconPlus />
            </span>
          }
          showChevron
          onClick={() => navigate('/templates/new')}
        />
      </CellList>

      <CellList mode="island" filled>
        <CellSimple
          title="Написать боту"
          subtitle="Текстом, голосом или фото"
          before={
            <span className="themed-icon">
              <IconChat />
            </span>
          }
          showChevron
          onClick={toChat}
        />
      </CellList>
      {chatHint ? (
        <div className="section">
          <Banner tone="info" title="Откройте чат с ботом в MAX">
            Например: «Счёт на 120 000 для ООО Ромашка»
          </Banner>
        </div>
      ) : null}
    </Page>
  );
}

function TemplateGrid({
  templates,
  onOpen,
}: {
  templates: Template[];
  onOpen: (template: Template) => void;
}) {
  return (
    <div className="templates">
      {templates.map((template) => (
        <button
          key={template.id}
          type="button"
          className="template-card"
          onClick={() => onOpen(template)}
        >
          <DocPreview text={template.preview} marks={false} mini />
          <Typography.Text variant="detail-strong">{template.title}</Typography.Text>
          {/* Метка только у своего шаблона: «Стандартный» под каждой карточкой
              ничего не различало. */}
          {template.is_builtin ? null : (
            <Typography.Text variant="description" color="tertiary">
              Ваш шаблон
            </Typography.Text>
          )}
        </button>
      ))}
    </div>
  );
}
