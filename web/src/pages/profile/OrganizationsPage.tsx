// Мои организации: ООО, ИП — всё, от чьего имени пользователь выставляет документы.
// Основная стоит первой: от неё документ, если организацию не выбрали.
import { Avatar, CellAction, CellHeader, CellList, CellSimple } from '@maxhub/max-ui';
import { useNavigate } from 'react-router-dom';

import { IconPlus } from '@/components/icons';
import { Page } from '@/components/Page';
import { EmptyState, ErrorState, Loading } from '@/components/StateViews';
import { useAuth } from '@/auth/context';
import { initials } from '@/lib/format';
import { useAsync } from '@/lib/useAsync';
import { useBack } from '@/lib/useBack';

export function OrganizationsPage() {
  const { api } = useAuth();
  const navigate = useNavigate();
  const back = useBack('/profile');
  const state = useAsync(() => api.organizations(), [api]);

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
        <CellList mode="island" filled header={<CellHeader>Все организации</CellHeader>}>
          {state.data.map((item) => (
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
              before={
                <Avatar.Container size={40}>
                  <Avatar.Text gradient="purple">{initials(item.name)}</Avatar.Text>
                </Avatar.Container>
              }
              showChevron
              onClick={() => navigate(`/profile/organizations/${item.id}`)}
            />
          ))}
        </CellList>
      ) : null}
    </Page>
  );
}
