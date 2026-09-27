// Итог: файл ушёл в чат с ботом. Главное действие — вернуться в чат,
// документ уже лежит в архиве.
import { Button, Typography } from '@maxhub/max-ui';
import { useLocation, useNavigate, useParams } from 'react-router-dom';

import { IconCheck } from '@/components/icons';
import { Page } from '@/components/Page';
import { closeApp, isInsideMax } from '@/max/webapp';

export function SentPage() {
  const navigate = useNavigate();
  const documentId = Number(useParams().documentId);
  const sent = useLocation().state as { filename?: string } | null;
  const inside = isInsideMax();

  return (
    <Page
      title=""
      footer={
        <>
          {inside ? (
            <Button size="large" stretched onClick={() => closeApp()}>
              Вернуться в чат
            </Button>
          ) : null}
          <Button
            size="large"
            variant={inside ? 'secondary' : 'primary'}
            stretched
            onClick={() => navigate(`/documents/${documentId}`, { replace: true })}
          >
            Открыть документ
          </Button>
          <Button
            size="large"
            variant="ghost"
            stretched
            onClick={() => navigate('/create', { replace: true })}
          >
            Создать ещё
          </Button>
        </>
      }
    >
      <div className="result">
        <span className="result__icon">
          <IconCheck size={40} />
        </span>
        <Typography.Text variant="header">Отправлено</Typography.Text>
        <Typography.Text variant="body" color="secondary">
          {sent?.filename ? `«${sent.filename}» придёт в чат` : 'Файл придёт в чат'} через пару
          секунд
        </Typography.Text>
      </div>
    </Page>
  );
}
