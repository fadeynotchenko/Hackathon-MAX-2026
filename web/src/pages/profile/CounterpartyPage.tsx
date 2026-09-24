// Карточка клиента: новая или существующая. Новая может открываться из
// создания документа — тогда после сохранения возвращаемся туда с её id.
import { Button, CellAction, CellList } from '@maxhub/max-ui';
import { useState } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';

import type { Counterparty } from '@/api/client';
import { Banner } from '@/components/Banner';
import { IconTrash } from '@/components/icons';
import { Page } from '@/components/Page';
import { ErrorState, Loading } from '@/components/StateViews';
import { useAuth } from '@/auth/context';
import { errorText, useAsync } from '@/lib/useAsync';
import { useBack } from '@/lib/useBack';
import { hapticResult } from '@/max/webapp';

import { RequisitesForm } from './RequisitesForm';
import { splitRequisiteErrors, type Requisites } from './requisites';

export function CounterpartyPage() {
  const { api } = useAuth();
  const param = useParams().counterpartyId;
  const isNew = param === undefined;
  const counterpartyId = Number(param);
  const back = useBack('/profile/counterparties');
  const state = useAsync<Counterparty | null>(
    () =>
      isNew
        ? Promise.resolve(null)
        : api
            .counterparties()
            .then((list) => list.find((item) => item.id === counterpartyId) ?? null),
    [api, counterpartyId, isNew],
  );

  if (isNew) return <CounterpartyForm initial={{}} counterpartyId={null} onBack={back} />;
  if (!state.data) {
    return (
      <Page title="Карточка клиента" onBack={back}>
        {state.loading ? (
          <Loading />
        ) : (
          <ErrorState message={state.error ?? 'Карточка не найдена'} onRetry={state.reload} />
        )}
      </Page>
    );
  }
  return (
    <CounterpartyForm
      key={state.data.id}
      initial={{ ...state.data.values, name: state.data.name }}
      counterpartyId={state.data.id}
      onBack={back}
    />
  );
}

interface CounterpartyFormProps {
  initial: Requisites;
  counterpartyId: number | null;
  onBack: () => void;
}

function CounterpartyForm({ initial, counterpartyId, onBack }: CounterpartyFormProps) {
  const { api } = useAuth();
  const navigate = useNavigate();
  const returnTo = (useLocation().state as { returnTo?: string } | null)?.returnTo;
  const isNew = counterpartyId === null;
  const title = isNew ? 'Новый клиент' : 'Карточка клиента';
  const [values, setValues] = useState<Requisites>(initial);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const save = async () => {
    setError(null);
    setErrors({});
    const name = values['name']?.trim() ?? '';
    if (!name) {
      setErrors({ name: 'Укажите название клиента' });
      return;
    }
    setSaving(true);
    try {
      const saved = isNew
        ? await api.createCounterparty({ name, values })
        : await api.updateCounterparty(counterpartyId, { name, values });
      hapticResult('success');
      if (returnTo) {
        void navigate(returnTo, { replace: true, state: { counterpartyId: saved.id } });
      } else {
        void navigate('/profile/counterparties', { replace: true });
      }
    } catch (err) {
      hapticResult('error');
      const split = splitRequisiteErrors(errorText(err, 'Не удалось сохранить'));
      setErrors(split.byField);
      setError(split.rest.join('; ') || 'Исправьте выделенные поля');
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    if (!confirmDelete) {
      setConfirmDelete(true);
      return;
    }
    if (counterpartyId === null || deleting) return;
    setDeleting(true);
    try {
      await api.deleteCounterparty(counterpartyId);
      void navigate('/profile/counterparties', { replace: true });
    } catch (err) {
      setError(errorText(err, 'Не удалось удалить карточку'));
      setDeleting(false);
    }
  };

  return (
    <Page
      title={title}
      subtitle="Реквизиты подставятся в документы для этого клиента"
      onBack={onBack}
      footer={
        <Button size="large" stretched loading={saving} onClick={() => void save()}>
          {isNew && returnTo ? 'Сохранить и продолжить' : 'Сохранить'}
        </Button>
      }
    >
      {error ? (
        <div className="section">
          <Banner tone="error" title={error} />
        </div>
      ) : null}
      <RequisitesForm values={values} onChange={setValues} errors={errors} />
      {!isNew ? (
        <CellList mode="island" filled>
          <CellAction
            before={<IconTrash />}
            mode="destructive"
            disabled={saving || deleting}
            onClick={() => void remove()}
          >
            {confirmDelete ? 'Нажмите ещё раз, чтобы удалить' : 'Удалить карточку'}
          </CellAction>
        </CellList>
      ) : null}
    </Page>
  );
}
