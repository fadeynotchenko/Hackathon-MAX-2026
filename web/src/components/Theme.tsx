// Провайдер дизайн-системы MAX: тема и платформа — из клиента MAX, вне него
// MAX UI берёт системную тему и платформу по user agent.
import { MaxUI } from '@maxhub/max-ui';
import { useEffect, useState, type ReactNode } from 'react';

import { getColorScheme, getPlatform, onThemeChange } from '@/max/webapp';

export function Theme({ children }: { children: ReactNode }) {
  const [colorScheme, setColorScheme] = useState(getColorScheme);
  useEffect(() => onThemeChange(() => setColorScheme(getColorScheme())), []);
  const platform = getPlatform();
  return (
    <MaxUI
      className="app"
      resetBody
      {...(colorScheme ? { colorScheme } : {})}
      {...(platform ? { platform } : {})}
    >
      {children}
    </MaxUI>
  );
}
