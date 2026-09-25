// Клиенты: карточки контрагентов, из которых подставляются реквизиты.
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

export function CounterpartiesPage() {
  const { api } = useAuth();
  const navigate = useNavigate();
  const back = useBack('/profile');
  const state = useAsync(() => api.counterparties(), [api]);
  const [query, setQuery] = useState('');
  const visible = state.data?.filter((item) => matchesCard(item, query)) ?? [];

  return (
    <Page title="Клиенты" subtitle="Карточки контрагентов" onBack={back}>
      <CellList mode="island" filled>
        <CellAction before={<IconPlus />} onClick={() => navigate('/profile/counterparties/new')}>
          Добавить клиента
        </CellAction>
      </CellList>
      {state.loading ? <Loading /> : null}
      {state.error ? <ErrorState message={state.error} onRetry={state.reload} /> : null}
      {state.data && state.data.length === 0 ? (
        <EmptyState
          title="Клиентов пока нет"
          text="Добавьте карточку вручную или по фото — реквизиты будут подставляться в документы."
        />
      ) : null}
      {state.data && state.data.length > 0 ? (
        <SearchField value={query} onChange={setQuery} hint="Название, ИНН или подписант" />
      ) : null}
      {state.data && state.data.length > 0 && visible.length === 0 ? (
        <EmptyState title="Ничего не нашлось" text="Попробуйте другое слово." />
      ) : null}
      {visible.length > 0 ? (
        <CellList mode="island" filled header={<CellHeader>Все клиенты</CellHeader>}>
          {visible.map((item) => (
            <CellSimple
              key={item.id}
              title={item.name}
              subtitle={item.inn ? `ИНН ${item.inn}` : 'ИНН не указан'}
              innerClassNames={{ title: 'clamp-2' }}
              showChevron
              onClick={() => navigate(`/profile/counterparties/${item.id}`)}
            />
          ))}
        </CellList>
      ) : null}
    </Page>
  );
}
