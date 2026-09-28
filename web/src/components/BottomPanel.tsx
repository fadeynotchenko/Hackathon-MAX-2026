// Панель снизу поверх экрана с затемнением: короткий выбор из пары действий,
// до которого тянуться большим пальцем. Тап по затемнению и Esc закрывают.
import { Button, Typography } from '@maxhub/max-ui';
import { useEffect, type ReactNode } from 'react';

export function BottomPanel({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <>
      <div className="bottom-panel__backdrop" onClick={onClose} />
      <div className="bottom-panel" role="dialog" aria-modal="true" aria-label={title}>
        <div className="bottom-panel__head">
          <Typography.Text variant="body-strong">{title}</Typography.Text>
          <Button size="small" variant="secondary" onClick={onClose}>
            Закрыть
          </Button>
        </div>
        <div className="bottom-panel__body">{children}</div>
      </div>
    </>
  );
}
