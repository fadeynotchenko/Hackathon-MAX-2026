// Экраны вне основного сценария: загрузка, запуск вне MAX, ошибка входа.
import { useAuth } from '@/auth/context';

export function GatePage() {
  const { status, error, retry } = useAuth();
  if (status === 'loading') {
    return (
      <main className="page">
        <p className="hint" role="status">
          Входим…
        </p>
      </main>
    );
  }
  if (status === 'signed_out') {
    return (
      <main className="page">
        <h1>Вы вышли</h1>
        <div className="card">
          <p className="hint">Откройте приложение заново, чтобы войти снова.</p>
        </div>
        <button className="button" type="button" onClick={retry}>
          Войти снова
        </button>
      </main>
    );
  }
  if (status === 'outside') {
    return (
      <main className="page">
        <h1>Откройте в MAX</h1>
        <div className="card">
          <p>Это мини-приложение работает внутри мессенджера MAX.</p>
          <p className="hint">
            На dev-стенде вход выполняется автоматически. Для production-сборки в браузере задайте
            VITE_DEV_INIT_DATA (cd core &amp;&amp; uv run python -m core.scripts.dev_init_data).
          </p>
        </div>
      </main>
    );
  }
  return (
    <main className="page">
      <h1>Не удалось войти</h1>
      <div className="card">
        <p className="status status--error" role="alert">
          {error}
        </p>
      </div>
      <button className="button" type="button" onClick={retry}>
        Попробовать снова
      </button>
    </main>
  );
}
