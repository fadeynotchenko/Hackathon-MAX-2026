// Шаг 2 из 3 — проверка. Документ так, как его соберёт шаблонизатор, и
// одна строка о том, что мешает двигаться дальше: не заполнено или распознанное
// ждёт «Всё верно». Распознанное без подтверждения дальше не пускает.
import { Button, CellHeader, CellList, CellSimple } from '@maxhub/max-ui';
import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import { Banner } from '@/components/Banner';
import { SheetPreview } from '@/components/SheetPreview';
import { Page } from '@/components/Page';
import { ErrorState, Loading } from '@/components/StateViews';
import { Steps } from '@/components/Steps';
import { useAuth } from '@/auth/context';
import { SOURCE_LABEL, displayValue } from '@/lib/format';
import { errorText, useAsync } from '@/lib/useAsync';
import { useBack } from '@/lib/useBack';
import { hapticResult } from '@/max/webapp';

import { documentTitle, fragmentLabel, labelsOf } from './fields';

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
      <Page title="Документ" onBack={back}>
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
  // Пустые поля отправку не держат (в файле останутся линии), ошибки — держат.
  const blocked = doc.errors.length > 0;
  const canExport = !pending && !blocked;

  const footer = pending ? (
    <>
      <Button size="large" stretched loading={confirming} onClick={() => void confirm()}>
        Всё верно
      </Button>
      <Button size="large" variant="ghost" stretched onClick={toFill}>
        Исправить
      </Button>
    </>
  ) : blocked ? (
    <Button size="large" stretched onClick={toFill}>
      Исправить ошибки
    </Button>
  ) : (
    // Вернуться к данным — «Назад»: вторая кнопка здесь только спорила бы с «Далее».
    <Button
      size="large"
      stretched
      disabled={!canExport}
      onClick={() => navigate(`/documents/${doc.id}/export`)}
    >
      Далее
    </Button>
  );

  return (
    <Page title={documentTitle(doc)} onBack={back} footer={footer}>
      <Steps current={2} />

      {error || blocked || doc.missing.length > 0 ? (
        <div className="section">
          {error ? (
            <Banner tone="error" title={error} />
          ) : blocked ? (
            <Banner tone="warning" title="Есть поля с ошибками" />
          ) : (
            <Banner
              tone="info"
              title={`Пустыми останутся: ${labelsOf(doc, doc.missing).join(', ')}`}
            >
              В файле на их месте будут линии — впишете от руки.
            </Banner>
          )}
        </div>
      ) : null}

      {pending ? (
        <CellList mode="island" filled header={<CellHeader>Сверьте с оригиналом</CellHeader>}>
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

      <div className="section">
        <SheetPreview
          source={{ kind: 'document', id: doc.id }}
          version={doc.updated_at}
          text={doc.preview}
        />
      </div>
    </Page>
  );
}
