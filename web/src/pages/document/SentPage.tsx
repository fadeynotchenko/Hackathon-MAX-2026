// Итог: файл ушёл в чат с ботом. Закрыть мини-апп можно системной кнопкой
// клиента, поэтому свои действия — только открыть документ или начать новый.
import { Button, Typography } from '@maxhub/max-ui';
import { useLocation, useNavigate, useParams } from 'react-router-dom';

import { IconCheck } from '@/components/icons';
import { Page } from '@/components/Page';

export function SentPage() {
  const navigate = useNavigate();
  const documentId = Number(useParams().documentId);
  const sent = useLocation().state as { filename?: string } | null;

  return (
    <Page
      title=""
      footer={
        <>
          <Button
            size="large"
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
