// Клиенты: карточки контрагентов, из которых подставляются реквизиты.
import { Avatar, CellAction, CellHeader, CellList, CellSimple } from '@maxhub/max-ui';
import { useNavigate } from 'react-router-dom';

import { IconPlus } from '@/components/icons';
import { Page } from '@/components/Page';
import { EmptyState, ErrorState, Loading } from '@/components/StateViews';
import { useAuth } from '@/auth/context';
import { initials } from '@/lib/format';
import { useAsync } from '@/lib/useAsync';
import { useBack } from '@/lib/useBack';

export function CounterpartiesPage() {
  const { api } = useAuth();
  const navigate = useNavigate();
  const back = useBack('/profile');
  const state = useAsync(() => api.counterparties(), [api]);

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
        <CellList mode="island" filled header={<CellHeader>Все клиенты</CellHeader>}>
          {state.data.map((item) => (
            <CellSimple
              key={item.id}
              title={item.name}
              subtitle={item.inn ? `ИНН ${item.inn}` : 'ИНН не указан'}
              innerClassNames={{ title: 'clamp-2' }}
              before={
                <Avatar.Container size={40}>
                  <Avatar.Text gradient="blue">{initials(item.name)}</Avatar.Text>
                </Avatar.Container>
              }
              showChevron
              onClick={() => navigate(`/profile/counterparties/${item.id}`)}
            />
          ))}
        </CellList>
      ) : null}
    </Page>
  );
}
