// «Для кого документ?» — карточка клиента выбирается до создания: сервер
// подставляет её реквизиты при создании черновика, поменять клиента у готового
// черновика API не умеет.
import { Avatar, CellAction, CellHeader, CellList, CellSimple } from '@maxhub/max-ui';
import { useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';

import { Banner } from '@/components/Banner';
import { IconEdit, IconPlus } from '@/components/icons';
import { Page } from '@/components/Page';
import { ErrorState, Loading } from '@/components/StateViews';
import { useAuth } from '@/auth/context';
import { initials } from '@/lib/format';
import { errorText, useAsync } from '@/lib/useAsync';

export function ClientPage() {
  const { api } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const templateId = Number(useParams().templateId);
  const counterparties = useAsync(() => api.counterparties(), [api]);
  const [creating, setCreating] = useState<number | 'none' | null>(null);
  const [error, setError] = useState<string | null>(null);
  const autoCreated = useRef(false);

  const create = async (counterpartyId: number | null) => {
    setCreating(counterpartyId ?? 'none');
    setError(null);
    try {
      const document = await api.createDocument({
        template_id: templateId,
        counterparty_id: counterpartyId,
      });
      void navigate(`/documents/${document.id}/fill`, { replace: true });
    } catch (err) {
      setError(errorText(err, 'Не удалось создать документ'));
      setCreating(null);
    }
  };

  // Вернулись с формы нового клиента — сразу создаём документ для него.
  const created = (location.state as { counterpartyId?: number } | null)?.counterpartyId;
  useEffect(() => {
    if (created === undefined || autoCreated.current) return;
    autoCreated.current = true;
    void create(created);
    // create стабилен по смыслу: templateId и api не меняются на экране.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [created]);

  const back = () => navigate(`/create/${templateId}`);
  const busy = creating !== null;

  return (
    <Page title="Для кого документ?" subtitle="Реквизиты клиента подставятся сами" onBack={back}>
      {error ? (
        <div className="section">
          <Banner tone="error" title={error} />
        </div>
      ) : null}
      <CellList mode="island" filled>
        <CellAction
          before={<IconPlus />}
          disabled={busy}
          onClick={() =>
            navigate('/profile/counterparties/new', {
              state: { returnTo: `/create/${templateId}/client` },
            })
          }
        >
          Новый клиент
        </CellAction>
        <CellAction
          before={<IconEdit />}
          mode="secondary"
          disabled={busy}
          onClick={() => void create(null)}
        >
          Без карточки — введу вручную
        </CellAction>
      </CellList>

      {counterparties.loading ? <Loading /> : null}
      {counterparties.error ? (
        <ErrorState message={counterparties.error} onRetry={counterparties.reload} />
      ) : null}
      {counterparties.data && counterparties.data.length > 0 ? (
        <CellList mode="island" filled header={<CellHeader>Ваши клиенты</CellHeader>}>
          {counterparties.data.map((item) => (
            <CellSimple
              key={item.id}
              title={item.name}
              subtitle={item.inn ? `ИНН ${item.inn}` : 'ИНН не указан'}
              before={
                <Avatar.Container size={40}>
                  <Avatar.Text gradient="blue">{initials(item.name)}</Avatar.Text>
                </Avatar.Container>
              }
              showChevron
              disabled={busy}
              onClick={() => void create(item.id)}
            />
          ))}
        </CellList>
      ) : null}
    </Page>
  );
}
