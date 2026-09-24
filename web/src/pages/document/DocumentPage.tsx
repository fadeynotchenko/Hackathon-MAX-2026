// Карточка документа из архива: состояние, путь (создан → отправлен →
// доставлен), предпросмотр и действия — продолжить, отправить, взять за основу.
import { Button, CellAction, CellHeader, CellList, CellSimple, Typography } from '@maxhub/max-ui';
import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import type { DocumentFact, DocumentView } from '@/api/client';
import { Banner, type BannerTone } from '@/components/Banner';
import { DocPreview } from '@/components/DocPreview';
import { IconCopy, IconEdit, IconSend, IconTrash } from '@/components/icons';
import { Page, Section } from '@/components/Page';
import { ErrorState, Loading } from '@/components/StateViews';
import { useAuth } from '@/auth/context';
import { FACT_LABEL, documentName, formatDate, formatDateTime } from '@/lib/format';
import { errorText, useAsync } from '@/lib/useAsync';
import { useBack } from '@/lib/useBack';

import { labelsOf } from './fields';

function statusBanner(
  doc: DocumentView,
  history: DocumentFact[],
): { tone: BannerTone; title: string; text?: string | undefined } {
  const last = [...history]
    .reverse()
    .find((fact) => ['sent', 'delivered', 'delivery_failed'].includes(fact.kind));
  const format = last?.format ? last.format.toUpperCase() : '';
  if (last?.kind === 'delivered') {
    return {
      tone: 'success',
      title: `${format} в чате`,
      text: `Доставлен ${formatDateTime(last.at)}`,
    };
  }
  if (last?.kind === 'delivery_failed') {
    return { tone: 'error', title: 'Файл не дошёл до чата', text: 'Отправьте его ещё раз.' };
  }
  if (last?.kind === 'sent') {
    return { tone: 'info', title: `${format} отправляется в чат`, text: formatDateTime(last.at) };
  }
  if (doc.ready && doc.unconfirmed.length === 0) {
    return { tone: 'info', title: 'Готов к отправке' };
  }
  const rest = [...doc.missing, ...doc.unconfirmed];
  return {
    tone: 'warning',
    title: 'Черновик',
    text: rest.length > 0 ? `Осталось: ${labelsOf(doc, rest).join(', ')}.` : undefined,
  };
}

export function DocumentPage() {
  const { api } = useAuth();
  const navigate = useNavigate();
  const documentId = Number(useParams().documentId);
  const back = useBack('/archive');
  const state = useAsync(
    () => Promise.all([api.document(documentId), api.documentHistory(documentId)]),
    [api, documentId],
  );
  const [busy, setBusy] = useState<'copy' | 'delete' | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!state.data) {
    return (
      <Page title="Документ" onBack={back}>
        {state.error ? <ErrorState message={state.error} onRetry={state.reload} /> : <Loading />}
      </Page>
    );
  }

  const [doc, facts] = state.data;
  // Отклонённые значения — для метрик, человеку в истории они не нужны.
  const history = facts.filter((fact) => fact.kind !== 'rejected');
  const ready = doc.ready && doc.unconfirmed.length === 0;
  const banner = statusBanner(doc, history);
  const client = doc.values['client_name']?.value;
  const subtitle = [doc.title !== doc.template.title ? doc.template.title : null, client]
    .filter(Boolean)
    .join(' · ');

  const copy = async () => {
    setBusy('copy');
    setError(null);
    try {
      const copied = await api.copyDocument(doc.id);
      void navigate(`/documents/${copied.id}/fill`);
    } catch (err) {
      setError(errorText(err, 'Не удалось создать копию'));
      setBusy(null);
    }
  };

  const remove = async () => {
    if (!confirmDelete) {
      setConfirmDelete(true);
      return;
    }
    setBusy('delete');
    try {
      await api.deleteDocument(doc.id);
      void navigate('/archive', { replace: true });
    } catch (err) {
      setError(errorText(err, 'Не удалось удалить документ'));
      setBusy(null);
    }
  };

  return (
    <Page
      title={documentName(doc.title, doc.values['number']?.value)}
      subtitle={subtitle || undefined}
      onBack={back}
      footer={
        ready ? (
          <Button
            size="large"
            stretched
            iconBefore={<IconSend size={20} />}
            onClick={() => navigate(`/documents/${doc.id}/export`)}
          >
            Отправить в чат
          </Button>
        ) : (
          <Button size="large" stretched onClick={() => navigate(`/documents/${doc.id}/fill`)}>
            Продолжить заполнение
          </Button>
        )
      }
    >
      <div className="section">
        <Banner tone={banner.tone} title={banner.title}>
          {banner.text}
        </Banner>
        {error ? <Banner tone="error" title={error} /> : null}
      </div>

      <CellList mode="island" filled>
        <CellAction before={<IconEdit />} onClick={() => navigate(`/documents/${doc.id}/fill`)}>
          Изменить данные
        </CellAction>
        <CellSimple
          title="На основе этого"
          subtitle="Новый документ: те же стороны и условия, новые номер и даты"
          before={
            <span className="themed-icon">
              <IconCopy />
            </span>
          }
          disabled={busy !== null}
          showChevron
          onClick={() => void copy()}
        />
      </CellList>

      <Section title="Как выглядит">
        <DocPreview text={doc.preview} />
      </Section>

      <CellList mode="island" filled header={<CellHeader>История</CellHeader>}>
        {history.length === 0 ? (
          <CellSimple height="compact" title={`Создан ${formatDate(doc.created_at)}`} />
        ) : (
          history.map((fact, index) => (
            <CellSimple
              key={`${fact.kind}-${fact.at}-${index}`}
              className="history-cell"
              separator={index < history.length - 1}
              title={
                fact.kind === 'created' && fact.source === 'copy'
                  ? 'Создан на основе другого'
                  : (FACT_LABEL[fact.kind] ?? fact.kind)
              }
              subtitle={formatDateTime(fact.at)}
              after={
                fact.format ? (
                  <Typography.Text variant="description" color="tertiary">
                    {fact.format.toUpperCase()}
                  </Typography.Text>
                ) : null
              }
            />
          ))
        )}
      </CellList>

      <CellList mode="island" filled>
        <CellAction
          before={<IconTrash />}
          mode="destructive"
          disabled={busy !== null}
          onClick={() => void remove()}
        >
          {confirmDelete ? 'Нажмите ещё раз, чтобы удалить' : 'Удалить документ'}
        </CellAction>
      </CellList>
    </Page>
  );
}
