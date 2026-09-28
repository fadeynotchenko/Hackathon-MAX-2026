// Стек экранов (lib/screenMemory): каждый экран истории остаётся смонтированным
// и скрытым, пока поверх открыт другой. Маршруты отдаёт вызывающий — приложение
// и тесты экранов рендерят одно и то же, поэтому «Назад» в тестах ведёт себя как
// в приложении.
import { useMemo, useState, type ReactNode } from 'react';
import { useLocation, type Location } from 'react-router-dom';

import { ScreenContext, useScreenStack } from '@/lib/screenMemory';

type RenderRoutes = (location: Location) => ReactNode;

// Экран стека помнит, сколько раз на него возвращались: по этому счётчику
// данные экрана тихо обновляются (lib/useAsync).
function StackedScreen({
  location,
  active,
  canGoBack,
  render,
}: {
  location: Location;
  active: boolean;
  canGoBack: boolean;
  render: RenderRoutes;
}) {
  const [returns, setReturns] = useState(0);
  const [wasActive, setWasActive] = useState(active);
  if (wasActive !== active) {
    setWasActive(active);
    if (active) setReturns((n) => n + 1);
  }
  const activity = useMemo(() => ({ active, returns, canGoBack }), [active, returns, canGoBack]);
  return (
    <ScreenContext.Provider value={activity}>
      <div
        data-screen={active ? 'active' : 'hidden'}
        hidden={!active}
        style={active ? { display: 'contents' } : undefined}
      >
        {render(location)}
      </div>
    </ScreenContext.Provider>
  );
}

export function ScreenStack({ children }: { children: RenderRoutes }) {
  const location = useLocation();
  const stack = useScreenStack();
  return stack.map((entry, index) => (
    <StackedScreen
      key={entry.key}
      location={entry}
      active={entry.key === location.key}
      canGoBack={index > 0}
      render={children}
    />
  ));
}
