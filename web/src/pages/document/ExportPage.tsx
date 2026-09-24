// Шаг 3 из 3 — экспорт. Формат и сопроводительный текст выбираются на одном
// экране, файл приходит в чат с ботом: оттуда человек пересылает его клиенту.
import {
  Button,
  CellAction,
  CellHeader,
  CellList,
  CellSimple,
  Radio,
  Switch,
  Textarea,
  Typography,
} from '@maxhub/max-ui';
import { useState } from 'react';
import { Navigate, useNavigate, useParams } from 'react-router-dom';

import { ApiError, type DocumentView, type FileFormat } from '@/api/client';
import { Banner } from '@/components/Banner';
import { IconSparkle } from '@/components/icons';
import { Page, Section } from '@/components/Page';
import { ErrorState, Loading } from '@/components/StateViews';
import { Steps } from '@/components/Steps';
import { useAuth } from '@/auth/context';
import { errorText, useAsync } from '@/lib/useAsync';
import { useBack } from '@/lib/useBack';
import { hapticResult } from '@/max/webapp';

import { defaultCoverText } from './fields';

const FORMATS: Array<{ format: FileFormat; title: string; subtitle: string }> = [
  { format: 'pdf', title: 'PDF', subtitle: 'Для отправки клиенту — выглядит одинаково везде' },
  { format: 'docx', title: 'DOCX', subtitle: 'Для правок — откроется в Word или «Р7‑Офис»' },
];

export function ExportPage() {
  const { api } = useAuth();
  const documentId = Number(useParams().documentId);
  const back = useBack(`/documents/${documentId}/review`);
  const state = useAsync(() => api.document(documentId), [api, documentId]);

  const doc = state.data;
  if (!doc) {
    return (
      <Page title="Выберите формат" onBack={back}>
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
        state: { filename: sent.filename, format: sent.format },
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
      title="Выберите формат"
      subtitle={`${doc.template.title} · ${doc.title}`}
      onBack={onBack}
      footer={
        <Button size="large" stretched loading={sending} onClick={() => void send()}>
          Отправить в чат
        </Button>
      }
    >
      <div className="section">
        <Steps current={3} />
      </div>
      {error ? (
        <div className="section">
          <Banner tone="error" title={error} />
        </div>
      ) : null}

      <CellList mode="island" filled header={<CellHeader>Формат файла</CellHeader>}>
        {FORMATS.map((item) => (
          <CellSimple
            key={item.format}
            as="label"
            title={item.title}
            subtitle={item.subtitle}
            after={
              <Radio
                name="format"
                value={item.format}
                checked={format === item.format}
                onChange={() => setFormat(item.format)}
              />
            }
          />
        ))}
      </CellList>

      <CellList mode="island" filled header={<CellHeader>Сопроводительный текст</CellHeader>}>
        <CellSimple
          as="label"
          title="Добавить текст к файлу"
          subtitle="Бот пришлёт его вместе с файлом — перешлите клиенту"
          after={<Switch checked={withText} onChange={(e) => setWithText(e.target.checked)} />}
        />
        {withText ? (
          <CellAction
            before={<IconSparkle />}
            disabled={drafting}
            onClick={() => void draftWithAssistant()}
          >
            {drafting ? 'Помощник пишет…' : 'Написать с помощником'}
          </CellAction>
        ) : null}
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
          <Typography.Text variant="description" color="tertiary" style={{ padding: '0 12px' }}>
            Файл и текст придут в чат с ботом. Контрагенту ничего не отправляется без вас.
          </Typography.Text>
        </Section>
      ) : null}
    </Page>
  );
}
