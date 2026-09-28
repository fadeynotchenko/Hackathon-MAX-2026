// Подтверждение в виде системного диалога. У моста MAX нет showConfirm, а
// window.confirm во встроенном браузере клиента может не показаться вовсе,
// поэтому диалог свой: затемнение, карточка по центру, две кнопки.
import { Button, Typography } from '@maxhub/max-ui';
import { useEffect, useId, type ReactNode } from 'react';

export interface ConfirmDialogProps {
  title: ReactNode;
  children?: ReactNode;
  confirmLabel: string;
  cancelLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  title,
  children,
  confirmLabel,
  cancelLabel,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const titleId = useId();
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onCancel();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onCancel]);

  return (
    <div className="dialog" onClick={onCancel}>
      <div
        className="dialog__card"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onClick={(event) => event.stopPropagation()}
      >
        <Typography.Text variant="header" id={titleId} className="dialog__title">
          {title}
        </Typography.Text>
        {children ? (
          <Typography.Text variant="body" color="secondary">
            {children}
          </Typography.Text>
        ) : null}
        <div className="dialog__actions">
          <Button size="large" stretched onClick={onConfirm}>
            {confirmLabel}
          </Button>
          <Button size="large" variant="ghost" stretched onClick={onCancel}>
            {cancelLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
