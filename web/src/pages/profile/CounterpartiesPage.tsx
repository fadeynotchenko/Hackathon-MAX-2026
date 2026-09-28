// Клиенты: карточки контрагентов, из которых подставляются реквизиты.
import { CellAction, CellList, CellSimple } from '@maxhub/max-ui';
import { useNavigate } from 'react-router-dom';

import { IconPlus } from '@/components/icons';
import { Page } from '@/components/Page';
import { SearchField } from '@/components/SearchField';
import { EmptyState, ErrorState, Loading } from '@/components/StateViews';
import { useAuth } from '@/auth/context';
import { matchesCard, needsSearch } from '@/lib/search';
import { useScreenState } from '@/lib/screenMemory';
import { useAsync } from '@/lib/useAsync';
import { useBack } from '@/lib/useBack';

export function CounterpartiesPage() {
  const { api } = useAuth();
  const navigate = useNavigate();
  const back = useBack('/profile');
  const state = useAsync(() => api.counterparties(), [api]);
  const [query, setQuery] = useScreenState('query', '');
  const visible = state.data?.filter((item) => matchesCard(item, query)) ?? [];

  return (
    <Page title="Клиенты" onBack={back}>
      {state.loading ? <Loading /> : null}
      {state.error ? <ErrorState message={state.error} onRetry={state.reload} /> : null}
      {needsSearch(state.data?.length ?? 0) ? (
        <SearchField value={query} onChange={setQuery} hint="Название или ИНН" />
      ) : null}
      {state.data && state.data.length > 0 && visible.length === 0 ? (
        <EmptyState title="Ничего не нашлось" />
      ) : null}
      {state.data ? (
        <CellList mode="island" filled>
          <CellAction before={<IconPlus />} onClick={() => navigate('/profile/counterparties/new')}>
            Добавить клиента
          </CellAction>
          {visible.map((item) => (
            <CellSimple
              key={item.id}
              title={item.name}
              subtitle={item.inn ? `ИНН ${item.inn}` : undefined}
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
