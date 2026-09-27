// «Для кого документ?» — карточка клиента и своя организация выбираются до
// создания: сервер подставляет их реквизиты при создании черновика, поменять
// стороны у готового черновика API не умеет. Выбранная организация живёт в адресе
// (?org=), чтобы пережить поход в форму нового клиента и обратно.
import { Button, CellAction, CellHeader, CellList, CellSimple, Radio } from '@maxhub/max-ui';
import { useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom';

import { Banner } from '@/components/Banner';
import { IconPlus } from '@/components/icons';
import { Page } from '@/components/Page';
import { SearchField } from '@/components/SearchField';
import { EmptyState, ErrorState, Loading } from '@/components/StateViews';
import { useAuth } from '@/auth/context';
import { matchesCard, needsSearch } from '@/lib/search';
import { errorText, useAsync } from '@/lib/useAsync';

export function ClientPage() {
  const { api } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const templateId = Number(useParams().templateId);
  const counterparties = useAsync(() => api.counterparties(), [api]);
  const organizations = useAsync(() => api.organizations(), [api]);
  const [params, setParams] = useSearchParams();
  const organizationId =
    Number(params.get('org')) || (organizations.data?.find((item) => item.is_default)?.id ?? null);
  const chooseOrganization = (id: number) => setParams({ org: String(id) }, { replace: true });
  const [creating, setCreating] = useState<number | 'none' | null>(null);
  const [error, setError] = useState<string | null>(null);
  const autoCreated = useRef(false);
  const [query, setQuery] = useState('');
  const clients = counterparties.data?.filter((item) => matchesCard(item, query)) ?? [];

  const create = async (counterpartyId: number | null) => {
    setCreating(counterpartyId ?? 'none');
    setError(null);
    try {
      const document = await api.createDocument({
        template_id: templateId,
        counterparty_id: counterpartyId,
        organization_id: organizationId,
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
  const manyOrganizations = (organizations.data?.length ?? 0) > 1;
  const busy = creating !== null;

  const allClients = counterparties.data ?? [];

  return (
    <Page title={manyOrganizations ? 'Стороны документа' : 'Для кого документ?'} onBack={back}>
      {error ? (
        <div className="section">
          <Banner tone="error" title={error} />
        </div>
      ) : null}
      {organizations.data && manyOrganizations ? (
        <CellList mode="island" filled header={<CellHeader>От кого</CellHeader>}>
          {organizations.data.map((item) => (
            <CellSimple
              key={item.id}
              title={item.name}
              innerClassNames={{ title: 'ellipsis' }}
              after={
                <Radio
                  name="organization"
                  value={String(item.id)}
                  checked={organizationId === item.id}
                  onChange={() => chooseOrganization(item.id)}
                />
              }
              onClick={() => chooseOrganization(item.id)}
            />
          ))}
        </CellList>
      ) : null}

      {counterparties.loading ? <Loading /> : null}
      {counterparties.error ? (
        <ErrorState message={counterparties.error} onRetry={counterparties.reload} />
      ) : null}
      {needsSearch(allClients.length) ? (
        <SearchField value={query} onChange={setQuery} hint="Название или ИНН" />
      ) : null}
      {allClients.length > 0 && clients.length === 0 ? (
        <EmptyState title="Ничего не нашлось" />
      ) : null}
      {/* Новый клиент — первой строкой того же списка: выбор и добавление в одном месте. */}
      <CellList
        mode="island"
        filled
        header={manyOrganizations ? <CellHeader>Для кого</CellHeader> : undefined}
      >
        <CellAction
          before={<IconPlus />}
          disabled={busy}
          onClick={() =>
            navigate('/profile/counterparties/new', {
              state: {
                returnTo: `/create/${templateId}/client${organizationId ? `?org=${organizationId}` : ''}`,
              },
            })
          }
        >
          Новый клиент
        </CellAction>
        {clients.map((item) => (
          <CellSimple
            key={item.id}
            title={item.name}
            subtitle={item.inn ? `ИНН ${item.inn}` : undefined}
            innerClassNames={{ title: 'clamp-2' }}
            showChevron
            disabled={busy}
            onClick={() => void create(item.id)}
          />
        ))}
      </CellList>
      <div className="section">
        <Button
          variant="ghost"
          size="medium"
          stretched
          disabled={busy}
          onClick={() => void create(null)}
        >
          Ввести вручную
        </Button>
      </div>
    </Page>
  );
}
