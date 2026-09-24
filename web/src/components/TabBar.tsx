// Нижняя навигация корневых экранов. Три раздела — как в макете: создать
// документ, архив созданного, профиль с реквизитами и контрагентами.
import { NavLink } from 'react-router-dom';

import { haptic } from '@/max/webapp';

import { IconArchive, IconCreate, IconProfile } from './icons';

const TABS = [
  { to: '/create', label: 'Создать', Icon: IconCreate },
  { to: '/archive', label: 'Архив', Icon: IconArchive },
  { to: '/profile', label: 'Профиль', Icon: IconProfile },
] as const;

export function TabBar() {
  return (
    <nav className="tabbar" aria-label="Разделы">
      {TABS.map(({ to, label, Icon }) => (
        <NavLink key={to} to={to} className="tabbar__item" onClick={() => haptic('light')}>
          <Icon size={26} />
          <span>{label}</span>
        </NavLink>
      ))}
    </nav>
  );
}
