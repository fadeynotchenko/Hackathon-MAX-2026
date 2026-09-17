import { Screen } from '@/components/Screen';
import { useAuth } from '@/auth/context';

function formatDate(value: string | null | undefined): string {
  if (!value) return '—';
  return new Date(value).toLocaleString('ru-RU');
}

export function ProfilePage() {
  const { user, logout } = useAuth();
  if (!user) return null;
  return (
    <Screen title="Профиль">
      <div className="card">
        <p>
          <strong>{user.display_name}</strong>
          {user.username ? <span className="hint"> @{user.username}</span> : null}
        </p>
        <p className="hint">ID в MAX: {user.max_user_id}</p>
        <p className="hint">Первый вход: {formatDate(user.created_at)}</p>
        <p className="hint">Последний вход: {formatDate(user.last_login_at)}</p>
        {user.is_admin ? <p className="hint">Роль: администратор</p> : null}
      </div>
      <button className="button button--secondary" type="button" onClick={() => void logout()}>
        Выйти
      </button>
    </Screen>
  );
}
