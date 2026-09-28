// Вкладка «Создать»: каталог шаблонов — единственная точка выбора бланка
// (в макете каталог жил и здесь, и в профиле). Первым — «Свой шаблон»: новый
// бланк из файла или текста, чтобы это действие не терялось под сеткой; рядом —
// «Свой документ»: файл, которого нет в каталоге, меняется без шаблона. Ниже —
// две подписанные сетки: «Мои шаблоны» (если есть) над «Стандартными». Поиск
// стоит над сетками и ищет по обеим. Второй вход — чат с ботом, в самом низу.
import { CellHeader, CellList, CellSimple, Typography } from '@maxhub/max-ui';
import { useNavigate } from 'react-router-dom';

import type { Template } from '@/api/client';
import { IconEdit, IconPlus, IconUpload } from '@/components/icons';
import { Page, Section } from '@/components/Page';
import { SearchField } from '@/components/SearchField';
import { EmptyState, ErrorState, Loading } from '@/components/StateViews';
import { DocPreview } from '@/components/DocPreview';
import { useAuth } from '@/auth/context';
import { kindStyle } from '@/lib/format';
import { matchesQuery, needsSearch } from '@/lib/search';
import { useScreenState } from '@/lib/screenMemory';
import { useAsync } from '@/lib/useAsync';
import { haptic } from '@/max/webapp';

import { catalogSections } from './catalog';

export function CreatePage() {
  const { api } = useAuth();
  const navigate = useNavigate();
  const templates = useAsync(() => api.templates(), [api]);
  const [query, setQuery] = useScreenState('query', '');
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

  const open = (template: Template) => {
    haptic('light');
    void navigate(`/create/${template.id}`);
  };

  return (
    <Page title="Новый документ" tabs>
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
      {templates.loading ? <Loading /> : null}
      {templates.error ? <ErrorState message={templates.error} onRetry={templates.reload} /> : null}
      {all.length > 0 && visible.length === 0 ? <EmptyState title="Ничего не нашлось" /> : null}
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
          <DocPreview text={template.preview} marks={false} mini />
          <Typography.Text variant="detail-strong">{template.title}</Typography.Text>
        </button>
      ))}
    </div>
  );
}
