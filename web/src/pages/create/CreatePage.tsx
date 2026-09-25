// Вкладка «Создать»: каталог шаблонов — единственная точка выбора бланка
// (в макете каталог жил и здесь, и в профиле). Второй вход — чат с ботом.
import { CellHeader, CellList, CellSimple, Typography } from '@maxhub/max-ui';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { Banner } from '@/components/Banner';
import { IconChat } from '@/components/icons';
import { Page, Section } from '@/components/Page';
import { SearchField } from '@/components/SearchField';
import { EmptyState, ErrorState, Loading } from '@/components/StateViews';
import { DocPreview } from '@/components/DocPreview';
import { useAuth } from '@/auth/context';
import { matchesQuery } from '@/lib/search';
import { useAsync } from '@/lib/useAsync';
import { closeApp, haptic } from '@/max/webapp';

export function CreatePage() {
  const { api, user } = useAuth();
  const navigate = useNavigate();
  const templates = useAsync(() => api.templates(), [api]);
  const [chatHint, setChatHint] = useState(false);
  const [query, setQuery] = useState('');
  const visible =
    templates.data?.filter((template) =>
      matchesQuery([template.title, template.description], query),
    ) ?? [];

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
      {visible.length > 0 ? (
        <Section title="Шаблоны">
          <div className="templates">
            {visible.map((template) => (
              <button
                key={template.id}
                type="button"
                className="template-card"
                onClick={() => {
                  haptic('light');
                  void navigate(`/create/${template.id}`);
                }}
              >
                <DocPreview text={template.preview} marks={false} mini />
                <Typography.Text variant="detail-strong">{template.title}</Typography.Text>
                <Typography.Text variant="description" color="tertiary">
                  {template.is_builtin ? 'Стандартный' : 'Ваш шаблон'}
                </Typography.Text>
              </button>
            ))}
          </div>
        </Section>
      ) : null}

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
