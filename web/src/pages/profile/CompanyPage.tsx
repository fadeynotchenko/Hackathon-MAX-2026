// «Моя организация»: реквизиты, которые подставляются во все документы
// стороной продавца. Заполняются один раз, сохраняются целиком.
import { Button } from '@maxhub/max-ui';
import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

import { Banner } from '@/components/Banner';
import { Page } from '@/components/Page';
import { ErrorState, Loading } from '@/components/StateViews';
import { useAuth } from '@/auth/context';
import { errorText, useAsync } from '@/lib/useAsync';
import { useBack } from '@/lib/useBack';
import { hapticResult } from '@/max/webapp';

import { RequisitesForm } from './RequisitesForm';
import { splitRequisiteErrors, type Requisites } from './requisites';

export function CompanyPage() {
  const { api } = useAuth();
  const back = useBack('/profile');
  const state = useAsync(() => api.company(), [api]);

  if (!state.data) {
    return (
      <Page title="Моя организация" onBack={back}>
        {state.error ? <ErrorState message={state.error} onRetry={state.reload} /> : <Loading />}
      </Page>
    );
  }
  return <CompanyForm initial={{ ...state.data.values, name: state.data.name }} onBack={back} />;
}

function CompanyForm({ initial, onBack }: { initial: Requisites; onBack: () => void }) {
  const { api } = useAuth();
  const navigate = useNavigate();
  const returnTo = (useLocation().state as { returnTo?: string } | null)?.returnTo;
  const [values, setValues] = useState<Requisites>(initial);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const save = async () => {
    setSaving(true);
    setError(null);
    setErrors({});
    try {
      const name = values['name']?.trim() ?? '';
      if (!name) {
        setErrors({ name: 'Укажите название организации' });
        return;
      }
      await api.saveCompany({ name, values });
      hapticResult('success');
      void navigate(returnTo ?? '/profile', { replace: true, state: { saved: 'company' } });
    } catch (err) {
      hapticResult('error');
      const split = splitRequisiteErrors(errorText(err, 'Не удалось сохранить'));
      setErrors(split.byField);
      setError(split.rest.join('; ') || 'Исправьте выделенные поля');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Page
      title="Моя организация"
      subtitle="Подставляется во все документы как ваша сторона"
      onBack={onBack}
      footer={
        <Button size="large" stretched loading={saving} onClick={() => void save()}>
          Сохранить
        </Button>
      }
    >
      {error ? (
        <div className="section">
          <Banner tone="error" title={error} />
        </div>
      ) : null}
      <RequisitesForm values={values} onChange={setValues} errors={errors} />
    </Page>
  );
}
