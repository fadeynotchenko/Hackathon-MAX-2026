// Экраны вне основного сценария: загрузка, запуск вне MAX, ошибка входа.
import { Button, Spinner, Typography } from '@maxhub/max-ui';

import { useAuth } from '@/auth/context';

function Gate({ title, text, action }: { title: string; text: string; action?: () => void }) {
  return (
    <div className="screen">
      <div className="center-state">
        <Typography.Text variant="header">{title}</Typography.Text>
        <Typography.Text variant="body" color="secondary" role="alert">
          {text}
        </Typography.Text>
        {action ? (
          <Button size="large" onClick={action}>
            Попробовать снова
          </Button>
        ) : null}
      </div>
    </div>
  );
}

export function GatePage() {
  const { status, error, retry } = useAuth();
  if (status === 'loading') {
    return (
      <div className="screen">
        <div className="center-state" role="status">
          <Spinner size={32} appearance="themed" />
          <Typography.Text variant="detail" color="secondary">
            Входим…
          </Typography.Text>
        </div>
      </div>
    );
  }
  if (status === 'signed_out') {
    return <Gate title="Вы вышли" text="Откройте приложение заново, чтобы войти." action={retry} />;
  }
  if (status === 'outside') {
    return (
      <Gate
        title="Откройте в MAX"
        text="Это мини-приложение работает внутри мессенджера MAX: откройте его из чата с ботом. Для разработки в браузере задайте VITE_DEV_INIT_DATA (cd core && uv run python -m core.scripts.dev_init_data)."
      />
    );
  }
  return <Gate title="Не удалось войти" text={error ?? 'Сервер недоступен'} action={retry} />;
}
