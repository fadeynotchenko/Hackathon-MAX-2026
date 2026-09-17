// Каркас экрана: заголовок, навигация, содержимое. Один на все страницы.
import { NavLink } from 'react-router-dom';
import type { ReactNode } from 'react';

import { useAuth } from '@/auth/context';

export interface ScreenProps {
  title: string;
  children: ReactNode;
}

export function Screen({ title, children }: ScreenProps) {
  const { user } = useAuth();
  return (
    <main className="page">
      <nav className="nav" aria-label="Разделы">
        <NavLink to="/" end>
          Главная
        </NavLink>
        <NavLink to="/profile">Профиль</NavLink>
        {user?.is_admin ? <NavLink to="/admin">Админ</NavLink> : null}
      </nav>
      <h1>{title}</h1>
      {children}
    </main>
  );
}
