// Плашка состояния: подсказка, успех, внимание, ошибка — один вид на всех
// экранах сценария (в макете одинаковые по смыслу плашки были разного вида).
import { Typography } from '@maxhub/max-ui';
import type { ReactNode } from 'react';

import { IconAlert, IconCheckCircle, IconInfo } from './icons';

export type BannerTone = 'info' | 'success' | 'warning' | 'error';

const ICONS = {
  info: IconInfo,
  success: IconCheckCircle,
  warning: IconAlert,
  error: IconAlert,
} as const;

export interface BannerProps {
  tone: BannerTone;
  title: ReactNode;
  children?: ReactNode;
}

export function Banner({ tone, title, children }: BannerProps) {
  const Icon = ICONS[tone];
  return (
    <div className={`banner banner--${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
      <span className="banner__icon">
        <Icon size={20} />
      </span>
      <div className="banner__content">
        <Typography.Text variant="detail-strong">{title}</Typography.Text>
        {children ? (
          <Typography.Text variant="description" color="secondary" asChild>
            <div>{children}</div>
          </Typography.Text>
        ) : null}
      </div>
    </div>
  );
}
