// Вкладка «Профиль»: кто вошёл, свои организации и клиенты —
// всё, что подставляется в документы. Каталог шаблонов живёт во вкладке
// «Создать», здесь на него только ссылка.
import { Avatar, Button, CellHeader, CellList, CellSimple, Typography } from '@maxhub/max-ui';
import { useNavigate } from 'react-router-dom';

import { IconBuilding, IconChart, IconTemplates, IconUsers } from '@/components/icons';
import { Page } from '@/components/Page';
import { useAuth } from '@/auth/context';
import { initials, pluralize } from '@/lib/format';
import { useAsync } from '@/lib/useAsync';

export function ProfilePage() {
  const { api, user, logout } = useAuth();
  const navigate = useNavigate();
  const state = useAsync(() => Promise.all([api.organizations(), api.counterparties()]), [api]);
  if (!user) return null;

  const [organizations, counterparties] = state.data ?? [null, null];
  const main = organizations?.find((item) => item.is_default) ?? organizations?.[0];
  const organizationsSubtitle = !organizations
    ? '…'
    : !main
      ? 'Не заполнено — заполните один раз'
      : organizations.length === 1
        ? main.name
        : `${main.name} и ещё ${organizations.length - 1}`;

  return (
    <Page title="Профиль" tabs>
      <CellList mode="island" filled>
        <CellSimple
          title={user.display_name}
          subtitle={user.username ? `@${user.username}` : `ID в MAX: ${user.max_user_id}`}
          before={
            <Avatar.Container size={56}>
              {user.photo_url ? (
                <Avatar.Image src={user.photo_url} alt="" />
              ) : (
                <Avatar.Text gradient="purple">{initials(user.display_name)}</Avatar.Text>
              )}
            </Avatar.Container>
          }
        />
      </CellList>

      <CellList mode="island" filled header={<CellHeader>Для документов</CellHeader>}>
        <CellSimple
          title="Мои организации"
          subtitle={organizationsSubtitle}
          innerClassNames={{ subtitle: 'ellipsis' }}
          before={<IconBuilding />}
          after={
            organizations && organizations.length === 0 ? (
              <Typography.Text variant="description" className="negative">
                Заполнить
              </Typography.Text>
            ) : null
          }
          showChevron
          onClick={() => navigate('/profile/organizations')}
        />
        <CellSimple
          title="Клиенты"
          subtitle={
            counterparties
              ? counterparties.length > 0
                ? `${counterparties.length} ${pluralize(counterparties.length, 'карточка', 'карточки', 'карточек')}`
                : 'Пока нет карточек'
              : '…'
          }
          before={<IconUsers />}
          showChevron
          onClick={() => navigate('/profile/counterparties')}
        />
        <CellSimple
          title="Шаблоны"
          subtitle="Счёт, КП, договор"
          before={<IconTemplates />}
          showChevron
          onClick={() => navigate('/create')}
        />
      </CellList>

      {user.is_admin ? (
        <CellList mode="island" filled header={<CellHeader>Администрирование</CellHeader>}>
          <CellSimple
            title="Метрики и рассылка"
            subtitle="Пользователи, документы, воронка; сообщения через бота"
            before={<IconChart />}
            showChevron
            onClick={() => navigate('/admin')}
          />
        </CellList>
      ) : null}

      <div className="section">
        <Button variant="ghost" size="medium" stretched onClick={() => void logout()}>
          Выйти
        </Button>
      </div>
    </Page>
  );
}
