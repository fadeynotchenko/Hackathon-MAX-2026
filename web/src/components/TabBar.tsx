// Нижняя навигация корневых экранов. Три раздела — как в макете: создать
// документ, архив созданного, профиль с реквизитами и контрагентами.
import { NavLink } from 'react-router-dom';

import { TAB_NAVIGATION } from '@/lib/screenMemory';
import { haptic } from '@/max/webapp';

import { TABS } from './tabs';

export function TabBar() {
  return (
    <nav className="tabbar" aria-label="Разделы">
      {TABS.map(({ to, label, Icon }) => (
        <NavLink
          key={to}
          to={to}
          state={TAB_NAVIGATION}
          className="tabbar__item"
          onClick={() => haptic('light')}
        >
          <Icon size={26} />
          <span>{label}</span>
        </NavLink>
      ))}
    </nav>
  );
}
