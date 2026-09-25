// Мои организации: ООО, ИП — всё, от чьего имени пользователь выставляет документы.
// Основная стоит первой: от неё документ, если организацию не выбрали.
import { CellAction, CellHeader, CellList, CellSimple } from '@maxhub/max-ui';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { IconPlus } from '@/components/icons';
import { Page } from '@/components/Page';
import { SearchField } from '@/components/SearchField';
import { EmptyState, ErrorState, Loading } from '@/components/StateViews';
import { useAuth } from '@/auth/context';
import { matchesCard } from '@/lib/search';
import { useAsync } from '@/lib/useAsync';
import { useBack } from '@/lib/useBack';

export function OrganizationsPage() {
  const { api } = useAuth();
  const navigate = useNavigate();
  const back = useBack('/profile');
  const state = useAsync(() => api.organizations(), [api]);
  const [query, setQuery] = useState('');
  const visible = state.data?.filter((item) => matchesCard(item, query)) ?? [];

  return (
    <Page title="Мои организации" subtitle="От их имени выставляются документы" onBack={back}>
      <CellList mode="island" filled>
        <CellAction before={<IconPlus />} onClick={() => navigate('/profile/organizations/new')}>
          Добавить организацию
        </CellAction>
      </CellList>
      {state.loading ? <Loading /> : null}
      {state.error ? <ErrorState message={state.error} onRetry={state.reload} /> : null}
      {state.data && state.data.length === 0 ? (
        <EmptyState
          title="Организаций пока нет"
          text="Добавьте ООО или ИП вручную или по фото карточки — реквизиты подставятся в документы."
        />
      ) : null}
      {state.data && state.data.length > 0 ? (
        <SearchField value={query} onChange={setQuery} hint="Название, ИНН или банк" />
      ) : null}
      {state.data && state.data.length > 0 && visible.length === 0 ? (
        <EmptyState title="Ничего не нашлось" text="Попробуйте другое слово." />
      ) : null}
      {visible.length > 0 ? (
        <CellList mode="island" filled header={<CellHeader>Все организации</CellHeader>}>
          {visible.map((item) => (
            <CellSimple
              key={item.id}
              title={item.name}
              subtitle={
                <>
                  {item.is_default ? <span className="themed">Основная · </span> : null}
                  {item.inn ? `ИНН ${item.inn}` : 'ИНН не указан'}
                </>
              }
              innerClassNames={{ title: 'clamp-2' }}
              showChevron
              onClick={() => navigate(`/profile/organizations/${item.id}`)}
            />
          ))}
        </CellList>
      ) : null}
    </Page>
  );
}
