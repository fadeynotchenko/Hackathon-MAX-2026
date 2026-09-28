// Карточка документа из архива: состояние одной строкой, действия, лист и
// история (создан → отправлен → доставлен) — по строке на событие.
import { Button, CellAction, CellHeader, CellList, CellSimple, Typography } from '@maxhub/max-ui';
import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import type { DocumentFact, DocumentView } from '@/api/client';
import { Banner, type BannerTone } from '@/components/Banner';
import { SheetPreview } from '@/components/SheetPreview';
import { IconCopy, IconEdit, IconSend, IconTemplates, IconTrash } from '@/components/icons';
import { Page } from '@/components/Page';
import { ErrorState, Loading } from '@/components/StateViews';
import { useAuth } from '@/auth/context';
import { FACT_LABEL, documentName, formatDate, formatDateTime } from '@/lib/format';
import { errorText, useAsync } from '@/lib/useAsync';
import { useBack } from '@/lib/useBack';

function statusBanner(
  doc: DocumentView,
  history: DocumentFact[],
): { tone: BannerTone; title: string } {
  const last = [...history]
    .reverse()
    .find((fact) => ['sent', 'delivered', 'delivery_failed'].includes(fact.kind));
  const format = last?.format ? last.format.toUpperCase() : '';
  if (last?.kind === 'delivered') return { tone: 'success', title: `${format} в чате` };
  if (last?.kind === 'delivery_failed') {
    return { tone: 'error', title: 'Файл не дошёл до чата — отправьте ещё раз' };
  }
  if (last?.kind === 'sent') return { tone: 'info', title: `${format} отправляется в чат` };
  if (doc.ready && doc.unconfirmed.length === 0) return { tone: 'info', title: 'Готов к отправке' };
  return { tone: 'warning', title: 'Черновик' };
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
  const [busy, setBusy] = useState<'copy' | 'delete' | 'keep' | null>(null);
  const [kept, setKept] = useState(false);
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
      // Карточка остаётся в стеке под формой копии.
      setBusy(null);
    } catch (err) {
      setError(errorText(err, 'Не удалось создать копию'));
      setBusy(null);
    }
  };

  // Документ по своему файлу: его шаблон можно оставить в каталоге для следующих.
  const keep = async () => {
    setBusy('keep');
    setError(null);
    try {
      await api.keepTemplate(doc.template.id);
      setKept(true);
    } catch (err) {
      setError(errorText(err, 'Не удалось сохранить шаблон'));
    } finally {
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
        <Banner tone={banner.tone} title={banner.title} />
        {error ? <Banner tone="error" title={error} /> : null}
      </div>

      <CellList mode="island" filled>
        {/* У черновика «Продолжить заполнение» уже внизу — второй вход в ту же форму лишний. */}
        {ready ? (
          <CellAction before={<IconEdit />} onClick={() => navigate(`/documents/${doc.id}/fill`)}>
            Изменить данные
          </CellAction>
        ) : null}
        <CellAction before={<IconCopy />} disabled={busy !== null} onClick={() => void copy()}>
          На основе этого
        </CellAction>
        {doc.template.can_keep && !kept ? (
          <CellAction
            before={<IconTemplates />}
            disabled={busy !== null}
            onClick={() => void keep()}
          >
            Сохранить как шаблон
          </CellAction>
        ) : null}
      </CellList>
      {kept ? (
        <div className="section">
          <Banner tone="success" title="Шаблон в каталоге">
            Следующий такой документ начните на вкладке «Создать».
          </Banner>
        </div>
      ) : null}

      <div className="section">
        <SheetPreview
          source={{ kind: 'document', id: doc.id }}
          version={doc.updated_at}
          text={doc.preview}
        />
      </div>

      <CellList mode="island" filled header={<CellHeader>История</CellHeader>}>
        {history.length === 0 ? (
          <CellSimple height="compact" title={`Создан ${formatDate(doc.created_at)}`} />
        ) : (
          history.map((fact, index) => (
            <CellSimple
              key={`${fact.kind}-${fact.at}-${index}`}
              height="compact"
              title={
                fact.kind === 'created' && fact.source === 'copy'
                  ? 'Создан на основе другого'
                  : fact.kind === 'created' && fact.source === 'file'
                    ? 'Создан по вашему файлу'
                    : (FACT_LABEL[fact.kind] ?? fact.kind)
              }
              after={
                <Typography.Text variant="description" color="tertiary" className="nowrap">
                  {[fact.format?.toUpperCase(), formatDateTime(fact.at)]
                    .filter(Boolean)
                    .join(' · ')}
                </Typography.Text>
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
          {confirmDelete ? 'Точно удалить?' : 'Удалить документ'}
        </CellAction>
      </CellList>
    </Page>
  );
}
