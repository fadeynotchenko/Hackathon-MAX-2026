// Сводка и отправка сообщения пользователю через бота. Доступна только админам:
// сервер отвечает 403, а профиль не показывает ссылку остальным.
import { Button, CellHeader, CellList, CellSimple, Input, Textarea } from '@maxhub/max-ui';
import { useEffect, useState, type FormEvent } from 'react';

import { ApiError, type AdminStats } from '@/api/client';
import { Banner } from '@/components/Banner';
import { Page, Section } from '@/components/Page';
import { Loading } from '@/components/StateViews';
import { useAuth } from '@/auth/context';
import { useBack } from '@/lib/useBack';

export function AdminPage() {
  const { api } = useAuth();
  const back = useBack('/profile');
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
    <Page title="Сводка и рассылка" onBack={back}>
      {error ? (
        <div className="section">
          <Banner tone="error" title={error} />
        </div>
      ) : null}
      {!stats && !error ? <Loading /> : null}
      {stats ? (
        <CellList mode="island" filled header={<CellHeader>Сводка</CellHeader>}>
          <CellSimple title="Пользователей" after={String(stats.users_total)} />
          <CellSimple title="Активны за сутки" after={String(stats.users_active_24h)} />
        </CellList>
      ) : null}
      <Section title="Сообщение через бота">
        <form className="fields" onSubmit={(e) => void submit(e)}>
          <Input
            aria-label="ID пользователя в MAX"
            placeholder="ID пользователя в MAX"
            inputMode="numeric"
            pattern="[0-9]+"
            value={maxUserId}
            onChange={(e) => setMaxUserId(e.target.value)}
            required
          />
          <Textarea
            aria-label="Текст сообщения"
            placeholder="Текст сообщения"
            mode="secondary"
            rows={3}
            value={text}
            onChange={(e) => setText(e.target.value)}
            required
          />
          <Button type="submit" size="large" stretched loading={sending}>
            Отправить через бота
          </Button>
          {result ? <Banner tone={result.ok ? 'success' : 'error'} title={result.text} /> : null}
        </form>
      </Section>
    </Page>
  );
}
