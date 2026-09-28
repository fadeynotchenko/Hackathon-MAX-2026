// Клиент документа из карточек: тап по карточке подставляет её реквизиты и
// возвращает в форму. Выбранная отмечена галочкой; «Без карточки» отвязывает её
// (подставленное из карточки уходит, набранное руками остаётся). «Новый клиент» —
// первой строкой: выбор и добавление в одном месте, новая карточка подставляется
// сразу после сохранения (parties.ts).
import { Button, CellAction, CellList, CellSimple } from '@maxhub/max-ui';
import { useNavigate, useParams } from 'react-router-dom';

import { Banner } from '@/components/Banner';
import { IconCheck, IconPlus } from '@/components/icons';
import { Page } from '@/components/Page';
import { SearchField } from '@/components/SearchField';
import { EmptyState, ErrorState, Loading } from '@/components/StateViews';
import { useAuth } from '@/auth/context';
import { matchesCard, needsSearch } from '@/lib/search';
import { useScreenState } from '@/lib/screenMemory';
import { useAsync } from '@/lib/useAsync';

import { partyPickPath, usePartyPick } from './parties';

export function ClientPickPage() {
  const { api } = useAuth();
  const navigate = useNavigate();
  const documentId = Number(useParams().documentId);
  const { back, busy, pending, error, pick } = usePartyPick(documentId, 'client');
  const state = useAsync(
    () => Promise.all([api.document(documentId), api.counterparties()]),
    [api, documentId],
  );
  const [query, setQuery] = useScreenState('query', '');
  const current = state.data?.[0].counterparty_id ?? null;
  const cards = state.data?.[1] ?? [];
  const visible = cards.filter((card) => matchesCard(card, query));
  const marked = pending === undefined ? current : pending;

  const addCard = () =>
    navigate('/profile/counterparties/new', {
      replace: true,
      state: { returnTo: partyPickPath(documentId, 'client') },
    });

  return (
    <Page title="Клиент" onBack={back}>
      {error ? (
        <div className="section">
          <Banner tone="error" title={error} />
        </div>
      ) : null}
      {state.loading ? <Loading /> : null}
      {state.error ? <ErrorState message={state.error} onRetry={state.reload} /> : null}
      {state.data ? (
        <>
          {needsSearch(cards.length) ? (
            <SearchField value={query} onChange={setQuery} hint="Название или ИНН" />
          ) : null}
          {cards.length > 0 && visible.length === 0 ? (
            <EmptyState title="Ничего не нашлось" />
          ) : null}
          <CellList mode="island" filled>
            <CellAction before={<IconPlus />} disabled={busy} onClick={addCard}>
              Новый клиент
            </CellAction>
            {visible.map((card) => (
              <CellSimple
                key={card.id}
                title={card.name}
                subtitle={card.inn ? `ИНН ${card.inn}` : undefined}
                innerClassNames={{ title: 'clamp-2' }}
                after={
                  marked === card.id ? (
                    <span className="themed-icon">
                      <IconCheck />
                      <span className="visually-hidden">Выбран</span>
                    </span>
                  ) : null
                }
                showChevron={marked !== card.id}
                disabled={busy}
                onClick={() => void pick(card.id, current)}
              />
            ))}
          </CellList>
          {cards.length === 0 ? (
            <EmptyState
              title="Карточек пока нет"
              text="Сохраните клиента — его реквизиты подставятся в этот документ и в следующие"
            />
          ) : null}
          {current !== null ? (
            <div className="section">
              <Button
                variant="ghost"
                size="medium"
                stretched
                disabled={busy && pending !== null}
                loading={pending === null}
                onClick={() => void pick(null, current)}
              >
                Без карточки
              </Button>
            </div>
          ) : null}
        </>
      ) : null}
    </Page>
  );
}
