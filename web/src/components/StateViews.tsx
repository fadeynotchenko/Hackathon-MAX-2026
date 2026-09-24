// Загрузка, ошибка и пустой список — одинаково на всех экранах.
import { Button, Spinner, Typography } from '@maxhub/max-ui';
import type { ReactNode } from 'react';

export function Loading({ label = 'Загружаем…' }: { label?: string }) {
  return (
    <div className="center-state" role="status">
      <Spinner size={28} appearance="themed" />
      <span className="visually-hidden">{label}</span>
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="center-state">
      <Typography.Text variant="title">Что-то пошло не так</Typography.Text>
      <Typography.Text variant="detail" color="secondary" role="alert">
        {message}
      </Typography.Text>
      {onRetry ? (
        <Button variant="secondary" size="medium" onClick={onRetry}>
          Попробовать снова
        </Button>
      ) : null}
    </div>
  );
}

export function EmptyState({
  title,
  text,
  action,
}: {
  title: string;
  text?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="center-state">
      <Typography.Text variant="title">{title}</Typography.Text>
      {text ? (
        <Typography.Text variant="detail" color="secondary">
          {text}
        </Typography.Text>
      ) : null}
      {action}
    </div>
  );
}
