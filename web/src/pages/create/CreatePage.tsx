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
import { matchesQuery } from '@/lib/search';
import { useAsync } from '@/lib/useAsync';
import { closeApp, haptic } from '@/max/webapp';

import { catalogSections } from './catalog';

export function CreatePage() {
  const { api, user } = useAuth();
  const navigate = useNavigate();
  const templates = useAsync(() => api.templates(), [api]);
  const [chatHint, setChatHint] = useState(false);
  const [query, setQuery] = useState('');
  const visible =
    templates.data?.filter((template) =>
      matchesQuery(
        [
          template.title,
          template.description,
          kindStyle(template.kind).short,
          kindStyle(template.kind).section,
        ],
        query,
      ),
    ) ?? [];

  const open = (template: Template) => {
    haptic('light');
    void navigate(`/create/${template.id}`);
  };

  const toChat = () => {
    if (!closeApp()) setChatHint(true);
  };

  return (
    <Page
      title="Создать документ"
      subtitle={user?.first_name ? `${user.first_name}, выберите шаблон` : 'Выберите шаблон'}
      tabs
    >
      {templates.loading ? <Loading /> : null}
      {templates.error ? <ErrorState message={templates.error} onRetry={templates.reload} /> : null}
      {templates.data && templates.data.length > 0 ? (
        <SearchField value={query} onChange={setQuery} hint="Счёт, договор, КП" />
      ) : null}
      {templates.data && templates.data.length > 0 && visible.length === 0 ? (
        <EmptyState title="Ничего не нашлось" text="Попробуйте другое слово." />
      ) : null}
      {catalogSections(visible).map(([title, list]) => (
        <Section key={title} title={title}>
          <TemplateGrid templates={list} onOpen={open} />
        </Section>
      ))}

      <CellList mode="island" filled header={<CellHeader>Свой шаблон</CellHeader>}>
        <CellSimple
          title="Из файла"
          subtitle="Ваш DOCX или PDF — места для данных найдём сами"
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
          subtitle="Реквизиты сторон вставляются из каталога"
          before={
            <span className="themed-icon">
              <IconPlus />
            </span>
          }
          showChevron
          onClick={() => navigate('/templates/new')}
        />
      </CellList>

      <CellList mode="island" filled header={<CellHeader>Или начните в чате</CellHeader>}>
        <CellSimple
          title="Написать боту"
          subtitle="Текст, голосовое, фото или файл — бот заполнит документ"
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
            Напишите, какой документ нужен, например: «Счёт на 120 000 для ООО Ромашка за разработку
            сайта».
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
          <Typography.Text variant="description" color="tertiary">
            {template.is_builtin ? 'Стандартный' : 'Ваш шаблон'}
          </Typography.Text>
        </button>
      ))}
    </div>
  );
}
