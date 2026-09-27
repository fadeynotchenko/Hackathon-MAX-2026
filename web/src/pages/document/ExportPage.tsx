// Шаг 3 из 3 — отправка. Формат и сопроводительный текст выбираются на одном
// экране, файл приходит в чат с ботом: оттуда человек пересылает его клиенту.
import { Button, CellList, CellSimple, Switch, Textarea, Typography } from '@maxhub/max-ui';
import { useState } from 'react';
import { Navigate, useNavigate, useParams } from 'react-router-dom';

import { ApiError, type DocumentView, type FileFormat } from '@/api/client';
import { Banner } from '@/components/Banner';
import { IconSparkle } from '@/components/icons';
import { Page, Section } from '@/components/Page';
import { Segmented } from '@/components/Segmented';
import { ErrorState, Loading } from '@/components/StateViews';
import { Steps } from '@/components/Steps';
import { useAuth } from '@/auth/context';
import { errorText, useAsync } from '@/lib/useAsync';
import { useBack } from '@/lib/useBack';
import { hapticResult } from '@/max/webapp';

import { defaultCoverText, documentTitle } from './fields';

const FORMATS: Array<{ value: FileFormat; title: string; note: string }> = [
  { value: 'pdf', title: 'PDF', note: 'Для клиента' },
  { value: 'docx', title: 'DOCX', note: 'Для правок' },
];

export function ExportPage() {
  const { api } = useAuth();
  const documentId = Number(useParams().documentId);
  const back = useBack(`/documents/${documentId}/review`);
  const state = useAsync(() => api.document(documentId), [api, documentId]);

  const doc = state.data;
  if (!doc) {
    return (
      <Page title="Документ" onBack={back}>
        {state.error ? <ErrorState message={state.error} onRetry={state.reload} /> : <Loading />}
      </Page>
    );
  }
  // Неготовый документ собрать нельзя (сервер ответит 409) — назад к проверке.
  if (!doc.ready || doc.unconfirmed.length > 0) {
    return <Navigate to={`/documents/${doc.id}/review`} replace />;
  }
  return <ExportForm key={doc.id} doc={doc} onBack={back} />;
}

function ExportForm({ doc, onBack }: { doc: DocumentView; onBack: () => void }) {
  const { api } = useAuth();
  const navigate = useNavigate();
  const [format, setFormat] = useState<FileFormat>('pdf');
  const [withText, setWithText] = useState(true);
  const [text, setText] = useState(() => defaultCoverText(doc));
  const [drafting, setDrafting] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const draftWithAssistant = async () => {
    setDrafting(true);
    setError(null);
    try {
      setText((await api.coverLetter(doc.id)).text);
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 503
          ? 'Помощник сейчас недоступен — отредактируйте текст сами'
          : errorText(err, 'Не удалось подготовить текст'),
      );
    } finally {
      setDrafting(false);
    }
  };

  const send = async () => {
    setSending(true);
    setError(null);
    try {
      const sent = await api.sendDocument(doc.id, format, withText ? text.trim() || null : null);
      hapticResult('success');
      void navigate(`/documents/${doc.id}/sent`, {
        replace: true,
        state: { filename: sent.filename },
      });
    } catch (err) {
      hapticResult('error');
      setError(
        err instanceof ApiError && err.code === 'render.pdf_unavailable'
          ? 'PDF сейчас не собирается — выберите DOCX'
          : errorText(err, 'Не удалось отправить файл'),
      );
      setSending(false);
    }
  };

  return (
    <Page
      title={documentTitle(doc)}
      onBack={onBack}
      footer={
        <Button size="large" stretched loading={sending} onClick={() => void send()}>
          Отправить в чат
        </Button>
      }
    >
      <Steps current={3} />
      {error ? (
        <div className="section">
          <Banner tone="error" title={error} />
        </div>
      ) : null}

      <Segmented
        name="format"
        label="Формат файла"
        options={FORMATS}
        value={format}
        onChange={setFormat}
      />

      <CellList mode="island" filled>
        <CellSimple
          as="label"
          title="Текст к файлу"
          after={<Switch checked={withText} onChange={(e) => setWithText(e.target.checked)} />}
        />
      </CellList>
      {withText ? (
        <Section>
          <Textarea
            aria-label="Сопроводительный текст"
            mode="primary"
            rows={5}
            maxLength={4000}
            value={text}
            onChange={(event) => setText(event.target.value)}
          />
          <button
            type="button"
            className="link-button"
            disabled={drafting}
            onClick={() => void draftWithAssistant()}
          >
            <IconSparkle size={20} />
            {drafting ? 'Помощник пишет…' : 'Написать с помощником'}
          </button>
        </Section>
      ) : null}
      <Typography.Text
        variant="description"
        color="tertiary"
        style={{ padding: '0 var(--spacing-size3xl)' }}
      >
        Файл придёт в ваш чат с ботом — оттуда перешлёте клиенту.
      </Typography.Text>
    </Page>
  );
}
