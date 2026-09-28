// Вкладка «Создать»: каталог шаблонов — единственная точка выбора бланка.
// Под заголовком сразу поиск и теги, ниже — сетки: «Мои шаблоны» (если есть)
// над стандартными. Свой шаблон и правка своего файла — за «+» в шапке:
// ячейки над поиском отодвигали каталог, ради которого сюда приходят.
import { Button, CellList, CellSimple, IconButton, Typography } from '@maxhub/max-ui';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import type { Template } from '@/api/client';
import { BottomPanel } from '@/components/BottomPanel';
import { IconEdit, IconPlus } from '@/components/icons';
import { FilterChips } from '@/components/FilterChips';
import { Page, Section } from '@/components/Page';
import { SearchField } from '@/components/SearchField';
import { EmptyState, ErrorState, Loading } from '@/components/StateViews';
import { SheetPreview } from '@/components/SheetPreview';
import { useAuth } from '@/auth/context';
import { asKind, kindStyle } from '@/lib/format';
import { matchesQuery } from '@/lib/search';
import { useScreenState } from '@/lib/screenMemory';
import { templateVersion } from '@/lib/templateVersion';
import { useAsync } from '@/lib/useAsync';
import { haptic } from '@/max/webapp';

import { OWN_TAG, catalogSections, catalogTags } from './catalog';

export function CreatePage() {
  const { api } = useAuth();
  const navigate = useNavigate();
  const templates = useAsync(() => api.templates(), [api]);
  const [query, setQuery] = useScreenState('query', '');
  // Тег: вид документа или «own» — свои шаблоны.
  const [tag, setTag] = useScreenState<string | null>('tag', null);
  const all = templates.data ?? [];
  const tags = catalogTags(all);
  const visible = all.filter(
    (template) =>
      (tag === null || (tag === OWN_TAG ? !template.is_builtin : asKind(template.kind) === tag)) &&
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

  const [adding, setAdding] = useState(false);

  const open = (template: Template) => {
    haptic('light');
    void navigate(`/create/${template.id}`);
  };

  return (
    <Page
      title="Новый документ"
      tabs
      headerAfter={
        <IconButton
          variant="secondary"
          size="medium"
          aria-label="Свой шаблон или свой файл"
          aria-expanded={adding}
          onClick={() => setAdding(true)}
        >
          <IconPlus />
        </IconButton>
      }
    >
      <SearchField value={query} onChange={setQuery} hint="Счёт, договор, КП" />
      {tags.length > 1 ? (
        <FilterChips label="Вид шаблона" options={tags} value={tag} onChange={setTag} />
      ) : null}
      {templates.loading ? <Loading /> : null}
      {templates.error ? <ErrorState message={templates.error} onRetry={templates.reload} /> : null}
      {all.length > 0 && visible.length === 0 ? (
        tag === OWN_TAG && !query.trim() ? (
          <EmptyState
            title="Своих шаблонов пока нет"
            text="Из своего документа или бланка — оформление сохранится."
            action={
              <Button onClick={() => navigate('/templates/upload')}>Сделать свой шаблон</Button>
            }
          />
        ) : (
          <EmptyState title="Ничего не нашлось" />
        )
      ) : null}
      {catalogSections(visible, all).map(([title, list]) => (
        <Section key={title} title={title}>
          <TemplateGrid templates={list} onOpen={open} />
        </Section>
      ))}

      {adding ? (
        <BottomPanel title="Своё" onClose={() => setAdding(false)}>
          <CellList mode="island" filled>
            <CellSimple
              title="Сделать свой шаблон"
              subtitle="Из своего файла или текстом"
              before={
                <span className="themed-icon">
                  <IconPlus />
                </span>
              }
              showChevron
              onClick={() => navigate('/templates/upload')}
            />
            <CellSimple
              title="Изменить свой файл"
              subtitle="Поменяем данные, оформление останется"
              before={
                <span className="themed-icon">
                  <IconEdit />
                </span>
              }
              showChevron
              onClick={() => navigate('/documents/import')}
            />
          </CellList>
        </BottomPanel>
      ) : null}
    </Page>
  );
}

// Метки «свой / стандартный» на карточке нет: это говорит заголовок раздела.
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
          <SheetPreview
            source={{ kind: 'template', id: template.id }}
            version={templateVersion(template)}
            text={template.preview}
            marks={false}
            mini
          />
          <Typography.Text variant="detail-strong">{template.title}</Typography.Text>
        </button>
      ))}
    </div>
  );
}
