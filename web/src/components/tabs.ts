// Разделы таб-бара. Отдельно от компонента: адреса вкладок нужны и памяти
// экранов, которая восстанавливает вкладку такой, какой её оставили.
import { IconArchive, IconCreate, IconProfile } from './icons';

export const TABS = [
  { to: '/create', label: 'Создать', Icon: IconCreate },
  { to: '/archive', label: 'Архив', Icon: IconArchive },
  { to: '/profile', label: 'Профиль', Icon: IconProfile },
] as const;

export const TAB_PATHS: readonly string[] = TABS.map((tab) => tab.to);
