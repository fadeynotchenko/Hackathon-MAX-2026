// Шаг 2 из 3 — проверка. Документ так, как его соберёт шаблонизатор, и
// одна плашка о состоянии: что не заполнено, что распознано и ждёт «Всё верно»,
// или что всё готово. Распознанное без подтверждения дальше не пускает.
import { Button, CellAction, CellHeader, CellList, CellSimple } from '@maxhub/max-ui';
import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import { Banner } from '@/components/Banner';
import { DocPreview } from '@/components/DocPreview';
import { IconEdit } from '@/components/icons';
import { Page, Section } from '@/components/Page';
import { ErrorState, Loading } from '@/components/StateViews';
import { Steps } from '@/components/Steps';
import { useAuth } from '@/auth/context';
import { SOURCE_LABEL, displayValue } from '@/lib/format';
import { errorText, useAsync } from '@/lib/useAsync';
import { useBack } from '@/lib/useBack';
import { hapticResult } from '@/max/webapp';

import { documentCaption, fragmentLabel, labelsOf } from './fields';

export function ReviewPage() {
  const { api } = useAuth();
  const navigate = useNavigate();
  const documentId = Number(useParams().documentId);
  const back = useBack(`/documents/${documentId}/fill`);
  const state = useAsync(() => api.document(documentId), [api, documentId]);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const doc = state.data;
  if (!doc) {
    return (
      <Page title="Проверьте документ" onBack={back}>
        {state.error ? <ErrorState message={state.error} onRetry={state.reload} /> : <Loading />}
      </Page>
    );
  }

  const toFill = () => navigate(`/documents/${doc.id}/fill`);
  const confirm = async () => {
    setConfirming(true);
    setError(null);
    try {
      state.setData(await api.confirmFields(doc.id));
      hapticResult('success');
    } catch (err) {
      setError(errorText(err, 'Не удалось подтвердить значения'));
    } finally {
      setConfirming(false);
    }
  };

  const fieldsByKey = new Map(doc.template.fields.map((field) => [field.key, field]));
  const pending = doc.unconfirmed.length > 0;
  const blocked = doc.errors.length > 0 || doc.missing.length > 0;
  const canExport = doc.ready && !pending && !blocked;

  const footer = pending ? (
    <>
      <Button size="large" stretched loading={confirming} onClick={() => void confirm()}>
        Всё верно
      </Button>
      <Button size="large" variant="secondary" stretched onClick={toFill}>
        Исправить
      </Button>
    </>
  ) : blocked ? (
    <Button size="large" stretched onClick={toFill}>
      Заполнить недостающее
    </Button>
  ) : (
    <Button
      size="large"
      stretched
      disabled={!canExport}
      onClick={() => navigate(`/documents/${doc.id}/export`)}
    >
      Выбрать формат файла
    </Button>
  );

  return (
    <Page title="Проверьте документ" subtitle={documentCaption(doc)} onBack={back} footer={footer}>
      <div className="section">
        <Steps current={2} />
      </div>

      <div className="section">
        {error ? <Banner tone="error" title={error} /> : null}
        {!error && blocked ? (
          <Banner tone="warning" title="Документ ещё не готов">
            {doc.missing.length > 0
              ? `Не заполнено: ${labelsOf(doc, doc.missing).join(', ')}.`
              : 'Есть поля с ошибками.'}
          </Banner>
        ) : null}
        {!error && !blocked && pending ? (
          <Banner tone="info" title="Проверьте распознанные значения">
            Сверьте их с оригиналом. Если всё верно — подтвердите, иначе исправьте в форме.
          </Banner>
        ) : null}
        {!error && canExport ? (
          <Banner tone="success" title="Все обязательные поля заполнены" />
        ) : null}
      </div>

      {pending ? (
        <CellList mode="island" filled header={<CellHeader>Ждут подтверждения</CellHeader>}>
          {doc.unconfirmed.map((key) => {
            const field = fieldsByKey.get(key);
            const value = doc.values[key];
            if (!field || !value) return null;
            return (
              <CellSimple
                key={key}
                overline={`${field.label} · ${SOURCE_LABEL[value.source]}`}
                title={displayValue(field.type, value.value)}
                subtitle={value.fragment ? fragmentLabel(value.source, value.fragment) : undefined}
                subtitleMode="tertiary"
              />
            );
          })}
        </CellList>
      ) : null}

      <Section title="Как будет выглядеть">
        <DocPreview text={doc.preview} />
      </Section>

      <CellList mode="island" filled>
        <CellAction before={<IconEdit />} onClick={toFill}>
          Изменить данные
        </CellAction>
      </CellList>
    </Page>
  );
}
