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
  const sent = useLocation().state as { filename?: string; format?: string } | null;
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
            Открыть в архиве
          </Button>
          <Button
            size="large"
            variant="ghost"
            stretched
            onClick={() => navigate('/create', { replace: true })}
          >
            Создать ещё документ
          </Button>
        </>
      }
    >
      <div className="result">
        <span className="result__icon">
          <IconCheck size={40} />
        </span>
        <Typography.Text variant="header">Документ отправлен</Typography.Text>
        <Typography.Text variant="body" color="secondary">
          {sent?.filename ? `Бот пришлёт «${sent.filename}» в чат` : 'Бот пришлёт файл в чат'} через
          несколько секунд. Перешлите его клиенту вместе с текстом.
        </Typography.Text>
        <Typography.Text variant="description" color="tertiary">
          Документ сохранён в архиве: там видно, дошёл ли файл до чата.
        </Typography.Text>
      </div>
    </Page>
  );
}
