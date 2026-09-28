// «От кого» документ: своя организация из профиля. Выбор подставляет её
// реквизиты вместо всех полей продавца и возвращает в форму; «Новая
// организация» ведёт в форму профиля, и сохранённая подставляется сразу
// (parties.ts). Отмечена та, от которой документ сейчас.
import { CellAction, CellList, CellSimple, Radio } from '@maxhub/max-ui';
import { useNavigate, useParams } from 'react-router-dom';

import { Banner } from '@/components/Banner';
import { IconPlus } from '@/components/icons';
import { Page } from '@/components/Page';
import { EmptyState, ErrorState, Loading } from '@/components/StateViews';
import { useAuth } from '@/auth/context';
import { useAsync } from '@/lib/useAsync';

import { partyPickPath, usePartyPick } from './parties';

export function SellerPickPage() {
  const { api } = useAuth();
  const navigate = useNavigate();
  const documentId = Number(useParams().documentId);
  const { back, busy, pending, error, pick } = usePartyPick(documentId, 'seller');
  const state = useAsync(
    () => Promise.all([api.document(documentId), api.organizations()]),
    [api, documentId],
  );
  const current = state.data?.[0].organization_id ?? null;
  const organizations = state.data?.[1] ?? [];
  const marked = pending === undefined ? current : pending;

  const addOrganization = () =>
    navigate('/profile/organizations/new', {
      replace: true,
      state: { returnTo: partyPickPath(documentId, 'seller') },
    });

  return (
    <Page title="От кого" onBack={back}>
      {error ? (
        <div className="section">
          <Banner tone="error" title={error} />
        </div>
      ) : null}
      {state.loading ? <Loading /> : null}
      {state.error ? <ErrorState message={state.error} onRetry={state.reload} /> : null}
      {state.data ? (
        <>
          <CellList mode="island" filled>
            <CellAction before={<IconPlus />} disabled={busy} onClick={addOrganization}>
              Новая организация
            </CellAction>
            {organizations.map((item) => (
              <CellSimple
                key={item.id}
                title={item.name}
                subtitle={
                  item.is_default || item.inn ? (
                    <>
                      {item.is_default ? 'Основная' : null}
                      {item.is_default && item.inn ? ' · ' : null}
                      {item.inn ? `ИНН ${item.inn}` : null}
                    </>
                  ) : undefined
                }
                innerClassNames={{ title: 'clamp-2' }}
                after={
                  <Radio
                    name="organization"
                    value={String(item.id)}
                    aria-label={item.name}
                    checked={marked === item.id}
                    disabled={busy}
                    onChange={() => void pick(item.id, current)}
                  />
                }
                disabled={busy}
                onClick={() => void pick(item.id, current)}
              />
            ))}
          </CellList>
          {organizations.length === 0 ? (
            <EmptyState
              title="Своих организаций пока нет"
              text="Добавьте реквизиты один раз — они будут подставляться в документы"
            />
          ) : null}
        </>
      ) : null}
    </Page>
  );
}
