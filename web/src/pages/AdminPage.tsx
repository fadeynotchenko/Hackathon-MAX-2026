// Сводка и отправка сообщения пользователю через бота. Доступна только админам:
// сервер отвечает 403, а навигация не показывает ссылку остальным.
import { useEffect, useState, type FormEvent } from 'react';

import { ApiError, type AdminStats } from '@/api/client';
import { Screen } from '@/components/Screen';
import { useAuth } from '@/auth/context';

export function AdminPage() {
  const { api } = useAuth();
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [maxUserId, setMaxUserId] = useState('');
  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState<{ text: string; ok: boolean } | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .adminStats()
      .then((data) => {
        if (!cancelled) setStats(data);
      })
      .catch((err: unknown) => {
        if (!cancelled)
          setError(err instanceof ApiError ? err.message : 'Не удалось загрузить сводку');
      });
    return () => {
      cancelled = true;
    };
  }, [api]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setSending(true);
    setResult(null);
    try {
      const response = await api.adminNotify({
        max_user_id: Number(maxUserId),
        text,
        format: null,
      });
      setResult({ text: `Отправлено, событие ${response.event_id}`, ok: true });
      setText('');
    } catch (err) {
      setResult({
        text: err instanceof ApiError ? err.message : 'Не удалось отправить',
        ok: false,
      });
    } finally {
      setSending(false);
    }
  };

  return (
    <Screen title="Администрирование">
      <div className="card">
        {error ? <p className="status status--error">{error}</p> : null}
        {stats ? (
          <>
            <p>Пользователей: {stats.users_total}</p>
            <p>Активны за сутки: {stats.users_active_24h}</p>
          </>
        ) : (
          !error && <p className="hint">Загрузка…</p>
        )}
      </div>
      <form className="card" onSubmit={(e) => void submit(e)}>
        <label htmlFor="max-user-id">ID пользователя в MAX</label>
        <input
          id="max-user-id"
          className="field"
          inputMode="numeric"
          pattern="[0-9]+"
          value={maxUserId}
          onChange={(e) => setMaxUserId(e.target.value)}
          required
        />
        <label htmlFor="notify-text">Текст</label>
        <textarea
          id="notify-text"
          className="field"
          rows={3}
          value={text}
          onChange={(e) => setText(e.target.value)}
          required
        />
        <button className="button" type="submit" disabled={sending}>
          Отправить через бота
        </button>
        {result ? (
          <p className={result.ok ? 'status' : 'status status--error'} role="status">
            {result.text}
          </p>
        ) : null}
      </form>
    </Screen>
  );
}
