// Каркас экрана: шапка с заголовком, содержимое, закреплённое действие снизу
// или таб-бар. «Назад» — системная кнопка клиента MAX; вне MAX (браузер
// разработчика) та же кнопка рисуется в шапке.
import { CellHeader, IconButton, Typography } from '@maxhub/max-ui';
import { useEffect, type ReactNode } from 'react';

import { hasBackButton, showBackButton } from '@/max/webapp';

import { IconBack } from './icons';
import { TabBar } from './TabBar';

export interface PageProps {
  title: ReactNode;
  subtitle?: ReactNode;
  // Обработчик «Назад»; без него экран корневой (вкладка).
  onBack?: () => void;
  tabs?: boolean;
  footer?: ReactNode;
  headerAfter?: ReactNode;
  children: ReactNode;
}

export function Page({ title, subtitle, onBack, tabs, footer, headerAfter, children }: PageProps) {
  useEffect(() => {
    if (!onBack) return;
    return showBackButton(onBack);
  }, [onBack]);

  const bodyClass = [
    'screen__body',
    tabs ? 'screen__body--with-tabs' : '',
    footer ? 'screen__body--with-footer' : '',
  ].join(' ');

  return (
    <div className="screen">
      <header className="screen__header">
        {onBack && !hasBackButton() ? (
          <IconButton
            className="screen__back"
            variant="ghost"
            size="medium"
            aria-label="Назад"
            onClick={onBack}
          >
            <IconBack />
          </IconButton>
        ) : null}
        <div className="screen__titles" style={{ flex: 1 }}>
          <Typography.Text variant="header" asChild>
            <h1 className="screen__title">{title}</h1>
          </Typography.Text>
          {subtitle ? (
            <Typography.Text variant="description" color="secondary">
              {subtitle}
            </Typography.Text>
          ) : null}
        </div>
        {headerAfter}
      </header>
      <main className={bodyClass}>{children}</main>
      {footer ? <div className="screen__footer">{footer}</div> : null}
      {tabs ? <TabBar /> : null}
    </div>
  );
}

export interface SectionProps {
  title?: ReactNode;
  after?: ReactNode;
  children: ReactNode;
}

// Раздел экрана не из ячеек (форма, карточки, предпросмотр) с тем же заголовком,
// что у CellList: отступы и капс совпадают со списками MAX UI.
export function Section({ title, after, children }: SectionProps) {
  return (
    <section className="section">
      {title ? <CellHeader after={after}>{title}</CellHeader> : null}
      {children}
    </section>
  );
}
