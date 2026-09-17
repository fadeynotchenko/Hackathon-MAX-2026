import { Screen } from '@/components/Screen';
import { useAuth } from '@/auth/context';
import { haptic } from '@/max/webapp';

export function HomePage() {
  const { user, mode } = useAuth();
  return (
    <Screen title={`Привет, ${user?.first_name || 'гость'}`}>
      <div className="card">
        <p>Это фундамент мини-приложения для MAX: вход по initData уже выполнен, сессия выдана.</p>
        <p className="hint">Дальше здесь появится ваша предметная логика.</p>
        {mode === 'dev' ? (
          <p className="hint">
            Dev-вход: приложение открыто вне клиента MAX тестовым пользователем
            {user?.is_admin ? ' с правами администратора' : ''}.
          </p>
        ) : null}
      </div>
      <button className="button" type="button" onClick={() => haptic('light')}>
        Проверить отклик
      </button>
    </Screen>
  );
}
