// Карточка своей организации: новая или существующая. Новая может открываться из
// формы документа («От кого») — тогда после сохранения возвращаемся к выбору
// организации с её id, и выбор сразу подставляет её в документ.
import { Button, CellAction, CellList } from '@maxhub/max-ui';
import { useState } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';

import type { Organization } from '@/api/client';
import { Banner } from '@/components/Banner';
import { IconCheckCircle, IconTrash } from '@/components/icons';
import { Page } from '@/components/Page';
import { ErrorState, Loading } from '@/components/StateViews';
import { useAuth } from '@/auth/context';
import { errorText, useAsync } from '@/lib/useAsync';
import { useBack } from '@/lib/useBack';
import { hapticResult } from '@/max/webapp';

import { RequisitesForm } from './RequisitesForm';
import { splitRequisiteErrors, type Requisites } from './requisites';

export function OrganizationPage() {
  const { api } = useAuth();
  const param = useParams().organizationId;
  const isNew = param === undefined;
  const organizationId = Number(param);
  const back = useBack('/profile/organizations');
  const state = useAsync<Organization | null>(
    () =>
      isNew
        ? Promise.resolve(null)
        : api
            .organizations()
            .then((list) => list.find((item) => item.id === organizationId) ?? null),
    [api, organizationId, isNew],
  );

  if (isNew) return <OrganizationForm organization={null} onBack={back} />;
  if (!state.data) {
    return (
      <Page title="Организация" onBack={back}>
        {state.loading ? (
          <Loading />
        ) : (
          <ErrorState message={state.error ?? 'Организация не найдена'} onRetry={state.reload} />
        )}
      </Page>
    );
  }
  return <OrganizationForm key={state.data.id} organization={state.data} onBack={back} />;
}

interface OrganizationFormProps {
  organization: Organization | null;
  onBack: () => void;
}

function OrganizationForm({ organization, onBack }: OrganizationFormProps) {
  const { api } = useAuth();
  const navigate = useNavigate();
  const returnTo = (useLocation().state as { returnTo?: string } | null)?.returnTo;
  const [values, setValues] = useState<Requisites>(
    organization ? { ...organization.values, name: organization.name } : {},
  );
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const save = async (makeDefault = false) => {
    setError(null);
    setErrors({});
    const name = values['name']?.trim() ?? '';
    if (!name) {
      setErrors({ name: 'Укажите название организации' });
      return;
    }
    setSaving(true);
    try {
      const body = { name, values, is_default: makeDefault };
      const saved = organization
        ? await api.updateOrganization(organization.id, body)
        : await api.createOrganization(body);
      hapticResult('success');
      if (returnTo) {
        void navigate(returnTo, { replace: true, state: { organizationId: saved.id } });
      } else {
        onBack();
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
    if (!organization || deleting) return;
    setDeleting(true);
    try {
      await api.deleteOrganization(organization.id);
      onBack();
    } catch (err) {
      setError(errorText(err, 'Не удалось удалить организацию'));
      setDeleting(false);
    }
  };

  return (
    <Page
      title={organization ? 'Организация' : 'Новая организация'}
      {...(organization?.is_default ? { subtitle: 'Основная' } : {})}
      onBack={onBack}
      footer={
        <Button size="large" stretched loading={saving} onClick={() => void save()}>
          {!organization && returnTo ? 'Сохранить и продолжить' : 'Сохранить'}
        </Button>
      }
    >
      {error ? (
        <div className="section">
          <Banner tone="error" title={error} />
        </div>
      ) : null}
      <RequisitesForm values={values} onChange={setValues} errors={errors} side="seller" />
      {organization ? (
        <CellList mode="island" filled>
          {!organization.is_default ? (
            <CellAction
              before={<IconCheckCircle />}
              disabled={saving || deleting}
              onClick={() => void save(true)}
            >
              Сделать основной
            </CellAction>
          ) : null}
          <CellAction
            before={<IconTrash />}
            mode="destructive"
            disabled={saving || deleting}
            onClick={() => void remove()}
          >
            {confirmDelete ? 'Точно удалить?' : 'Удалить организацию'}
          </CellAction>
        </CellList>
      ) : null}
    </Page>
  );
}
