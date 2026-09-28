// Вкладка «Создать»: каталог шаблонов — единственная точка выбора бланка
// (в макете каталог жил и здесь, и в профиле). Первым — «Свой шаблон»: новый
// бланк из файла или текста, чтобы это действие не терялось под сеткой; рядом —
// «Свой документ»: файл, которого нет в каталоге, меняется без шаблона. Ниже —
// две подписанные сетки: «Мои шаблоны» (если есть) над «Стандартными». Поиск
// стоит над сетками и ищет по обеим. Второй вход — чат с ботом, в самом низу.
import { CellHeader, CellList, CellSimple, Typography } from '@maxhub/max-ui';
import { useNavigate } from 'react-router-dom';

import type { Template } from '@/api/client';
import { IconEdit, IconPlus } from '@/components/icons';
import { FilterChips } from '@/components/FilterChips';
import { Page, Section } from '@/components/Page';
import { SearchField } from '@/components/SearchField';
import { EmptyState, ErrorState, Loading } from '@/components/StateViews';
import { SheetPreview } from '@/components/SheetPreview';
import { useAuth } from '@/auth/context';
import { asKind, kindStyle } from '@/lib/format';
import { matchesQuery, needsSearch } from '@/lib/search';
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

  const open = (template: Template) => {
    haptic('light');
    void navigate(`/create/${template.id}`);
  };

  return (
    <Page title="Новый документ" tabs>
      <CellList mode="island" filled header={<CellHeader>Свой шаблон</CellHeader>}>
        {/* Один вход вместо «Из файла» и «Написать текст»: выбор между ними —
            уже на экране шаблона, где видно, чем они отличаются. */}
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
      </CellList>

      <CellList mode="island" filled header={<CellHeader>Свой документ</CellHeader>}>
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

      {needsSearch(all.length) ? (
        <SearchField value={query} onChange={setQuery} hint="Счёт, договор, КП" />
      ) : null}
      {needsSearch(all.length) && tags.length > 1 ? (
        <FilterChips label="Вид шаблона" options={tags} value={tag} onChange={setTag} />
      ) : null}
      {templates.loading ? <Loading /> : null}
      {templates.error ? <ErrorState message={templates.error} onRetry={templates.reload} /> : null}
      {all.length > 0 && visible.length === 0 ? (
        tag === OWN_TAG && !query.trim() ? (
          <EmptyState
            title="Своих шаблонов пока нет"
            text="Сделайте его из файла или текста — «Свой шаблон» вверху экрана."
          />
        ) : (
          <EmptyState title="Ничего не нашлось" />
        )
      ) : null}
      {/* Заголовок и у единственной сетки: «Стандартные» под «Своим шаблоном»
          говорит, что это общие бланки, а свой делается выше. */}
      {catalogSections(visible, all).map(([title, list]) => (
        <Section key={title} title={title}>
          <TemplateGrid templates={list} onOpen={open} />
        </Section>
      ))}
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
