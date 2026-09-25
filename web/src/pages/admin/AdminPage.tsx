// Метрики для владельца продукта и сообщение пользователю через бота. Доступно
// только админам: сервер отвечает 403, а профиль не показывает ссылку остальным.
// Данные — GET /admin/metrics за выбранный период; графики строятся из них без
// отдельного хранилища (docs/PRODUCT.md, пункт 17).
import {
  Button,
  CellHeader,
  CellList,
  CellSimple,
  Input,
  Textarea,
  Typography,
} from '@maxhub/max-ui';
import { useState, type FormEvent, type ReactNode } from 'react';

import { ApiError, type AdminMetrics, type DailyMetrics } from '@/api/client';
import { useAuth } from '@/auth/context';
import { Banner } from '@/components/Banner';
import { BarList, type BarRow } from '@/components/charts/BarList';
import { ColumnChart, type Column } from '@/components/charts/ColumnChart';
import { LineChart } from '@/components/charts/LineChart';
import { ChartCard, ChartTable, Legend } from '@/components/charts/parts';
import { IconAlert, IconCheckCircle, IconClock } from '@/components/icons';
import { Page, Section } from '@/components/Page';
import { ErrorState, Loading } from '@/components/StateViews';
import { formatNumber, kindStyle } from '@/lib/format';
import { useAsync } from '@/lib/useAsync';
import { useBack } from '@/lib/useBack';

import {
  autofillRows,
  DEFAULT_PERIOD,
  formatDay,
  formatMinutes,
  formatMs,
  formatPeriod,
  formatShare,
  formatsTotal,
  funnelRows,
  kindsTotal,
  PERIODS,
  rejectionRows,
  summarize,
  sumOf,
  toBuckets,
  type Bucket,
  type Row,
} from './metrics';

export function AdminPage() {
  const { api } = useAuth();
  const back = useBack('/profile');
  const [days, setDays] = useState<number>(DEFAULT_PERIOD);
  const state = useAsync(() => api.adminMetrics(days), [api, days]);
  // Смена периода держит прежние графики полупрозрачными, пока не придут новые:
  // без спиннера на весь экран и прыжка раскладки.
  const [shown, setShown] = useState<AdminMetrics | null>(null);
  if (state.data && state.data !== shown) setShown(state.data);
  const metrics = state.data ?? shown;

  return (
    <Page
      title="Метрики"
      {...(metrics ? { subtitle: formatPeriod(metrics.since, metrics.until) } : {})}
      onBack={back}
    >
      <div className="chips" role="group" aria-label="Период">
        {PERIODS.map((period) => (
          <Button
            key={period.days}
            size="small"
            variant={period.days === days ? 'primary' : 'secondary'}
            aria-pressed={period.days === days}
            onClick={() => setDays(period.days)}
          >
            {period.label}
          </Button>
        ))}
      </div>
      {!metrics && state.loading ? <Loading /> : null}
      {!metrics && state.error ? <ErrorState message={state.error} onRetry={state.reload} /> : null}
      {metrics && state.error ? (
        <div className="section">
          <Banner tone="error" title={state.error} />
        </div>
      ) : null}
      {metrics ? <Dashboard metrics={metrics} stale={state.loading} /> : null}
      <NotifySection />
    </Page>
  );
}

function StatTile({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className="stat-tile">
      <Typography.Text variant="description" color="secondary">
        {label}
      </Typography.Text>
      <Typography.Text variant="header" className="stat-tile__value">
        {value}
      </Typography.Text>
      <Typography.Text variant="description" color="tertiary">
        {note}
      </Typography.Text>
    </div>
  );
}

function shareNote(rows: Row[]): BarRow[] {
  return rows.map(({ share, ...row }) =>
    share === null || share === undefined ? row : { ...row, note: formatShare(share) },
  );
}

function columnsOf(
  buckets: Bucket[],
  pick: (day: DailyMetrics) => number,
  details?: (days: DailyMetrics[]) => Column['details'],
): Column[] {
  return buckets.map((bucket) => {
    const extra = details?.(bucket.days);
    return {
      key: bucket.key,
      label: bucket.label,
      value: sumOf(bucket.days, pick),
      ...(extra ? { details: extra } : {}),
    };
  });
}

// Разбивка столбца документов для подсказки: виды и копии прошлых.
function documentDetails(days: DailyMetrics[]): Column['details'] {
  const kinds = new Map<string, number>();
  for (const day of days) {
    for (const [kind, count] of Object.entries(day.created_by_kind)) {
      kinds.set(kind, (kinds.get(kind) ?? 0) + count);
    }
  }
  const rows = [...kinds.entries()]
    .filter(([, count]) => count > 0)
    .sort(([, a], [, b]) => b - a)
    .map(([kind, count]) => ({
      key: kind,
      name: kindStyle(kind).plural,
      value: formatNumber(count),
    }));
  const copied = sumOf(days, (day) => day.documents_copied);
  if (copied) {
    rows.push({ key: 'copied', name: 'на основе прошлых', value: formatNumber(copied) });
  }
  return rows;
}

function tableRows(columns: Column[]): string[][] {
  return columns.map((column) => [column.label, formatNumber(column.value)]);
}

function Muted({ children }: { children: ReactNode }) {
  return (
    <Typography.Text variant="description" color="secondary">
      {children}
    </Typography.Text>
  );
}

function Dashboard({ metrics, stale }: { metrics: AdminMetrics; stale: boolean }) {
  const summary = summarize(metrics);
  const buckets = toBuckets(metrics.daily);
  const step = buckets.weekly ? 'по неделям' : 'по дням';
  const dayLabels = metrics.daily.map((day) => formatDay(day.day));
  const newUsers = columnsOf(buckets.items, (day) => day.users_new);
  const created = columnsOf(buckets.items, (day) => day.documents_created, documentDetails);
  const kinds = kindsTotal(metrics.daily);
  const formats = formatsTotal(metrics.daily);
  const funnel = funnelRows(metrics.funnel);
  const autofill = autofillRows(metrics.autofill);
  const rejections = rejectionRows(metrics.rejections);
  const { deliveries } = metrics;
  const toSend = metrics.time_to_send_minutes;
  const renders = Object.entries(metrics.render_ms).sort(([a], [b]) => a.localeCompare(b));

  return (
    <div className={stale ? 'dashboard dashboard--stale' : 'dashboard'} aria-busy={stale}>
      <div className="section stat-grid">
        <StatTile
          label="Пользователей"
          value={formatNumber(summary.usersTotal)}
          note={`+${formatNumber(summary.usersNew)} за период`}
        />
        <StatTile
          label="Активны за 7 дней"
          value={formatNumber(summary.activeWeek)}
          note={`сегодня ${formatNumber(summary.activeToday)}`}
        />
        <StatTile
          label="Документов создано"
          value={formatNumber(summary.documentsCreated)}
          note={
            summary.documentsCopied
              ? `${formatNumber(summary.documentsCopied)} на основе прошлых`
              : 'за период'
          }
        />
        <StatTile
          label="Автозаполнение"
          value={formatShare(summary.automaticShare)}
          note="полей заполнено не вручную"
        />
      </div>

      <Section title="Пользователи">
        <ChartCard
          title="Активные пользователи"
          subtitle="Заходили в мини-апп или писали боту, по дням"
          legend={
            <Legend
              items={[
                { key: 'day', label: 'За день', tone: 'accent', shape: 'line' },
                { key: 'week', label: 'За 7 дней', tone: 'context', shape: 'line' },
              ]}
            />
          }
          table={
            <ChartTable
              columns={['День', 'За день', 'За 7 дней']}
              rows={metrics.daily.map((day) => [
                formatDay(day.day),
                formatNumber(day.active_day),
                formatNumber(day.active_week),
              ])}
            />
          }
        >
          <LineChart
            label="Активные пользователи по дням"
            labels={dayLabels}
            series={[
              {
                key: 'week',
                name: 'За 7 дней',
                tone: 'context',
                values: metrics.daily.map((day) => day.active_week),
              },
              {
                key: 'day',
                name: 'За день',
                tone: 'accent',
                values: metrics.daily.map((day) => day.active_day),
              },
            ]}
          />
        </ChartCard>
        <ChartCard
          title="Новые пользователи"
          subtitle={step}
          table={<ChartTable columns={['Период', 'Новых']} rows={tableRows(newUsers)} />}
        >
          <ColumnChart columns={newUsers} name="Новых" label={`Новые пользователи ${step}`} />
        </ChartCard>
      </Section>

      <Section title="Документы">
        <ChartCard
          title="Создано документов"
          subtitle={step}
          table={<ChartTable columns={['Период', 'Создано']} rows={tableRows(created)} />}
        >
          <ColumnChart columns={created} name="Создано" label={`Создано документов ${step}`} />
        </ChartCard>
        <ChartCard title="По видам" subtitle="Документы, созданные за период">
          {kinds.length ? (
            <BarList rows={kinds} label="Документы по видам" />
          ) : (
            <Muted>За период документов не создавали.</Muted>
          )}
        </ChartCard>
        <ChartCard title="Собрано файлов" subtitle="По формату">
          <BarList rows={formats} label="Собрано файлов по формату" />
        </ChartCard>
      </Section>

      <Section title="Воронка">
        <ChartCard
          title="Путь документа"
          subtitle="Документы, созданные за период: сколько из них дошли до каждого шага"
        >
          <BarList rows={shareNote(funnel)} label="Воронка документов" ordinal />
        </ChartCard>
      </Section>

      <Section title="Автозаполнение">
        <ChartCard
          title="Откуда значения полей"
          subtitle={`Не вручную — ${formatShare(metrics.autofill.automatic_share)} из ${formatNumber(metrics.autofill.total)} полей`}
        >
          {autofill.length ? (
            <BarList rows={shareNote(autofill)} label="Поля документов по источнику" />
          ) : (
            <Muted>За период полей не заполняли.</Muted>
          )}
        </ChartCard>
      </Section>

      <Section title="Пойманные ошибки">
        <ChartCard
          title="Проверка остановила"
          subtitle="Неверные реквизиты и значения, которые не попали в документ"
        >
          {rejections.length ? (
            <BarList rows={rejections} label="Ошибки по видам" />
          ) : (
            <Muted>За период проверка ничего не остановила.</Muted>
          )}
        </ChartCard>
      </Section>

      <CellList mode="island" filled header={<CellHeader>Доставка и скорость</CellHeader>}>
        <CellSimple
          before={<IconCheckCircle className="status-icon status-icon--good" />}
          title="Доставлено в чат"
          after={formatNumber(deliveries.delivered)}
        />
        <CellSimple
          before={<IconAlert className="status-icon status-icon--bad" />}
          title="Не дошло до чата"
          after={formatNumber(deliveries.failed)}
        />
        <CellSimple
          before={<IconClock className="status-icon status-icon--wait" />}
          title="Ждут подтверждения бота"
          after={formatNumber(deliveries.pending)}
        />
        <CellSimple
          title="От создания до отправки"
          subtitle={
            toSend.count
              ? `Медиана по ${formatNumber(toSend.count)} документам; 90\u00a0% — быстрее ${formatMinutes(toSend.p90)}`
              : 'За период отправок не было'
          }
          after={<span className="nowrap">{formatMinutes(toSend.median)}</span>}
        />
        {renders.map(([format, timing]) => (
          <CellSimple
            key={format}
            title={`Сборка ${format.toUpperCase()}`}
            subtitle={`Медиана по ${formatNumber(timing.count)} файлам; 90\u00a0% — быстрее ${formatMs(timing.p90)}`}
            after={<span className="nowrap">{formatMs(timing.median)}</span>}
          />
        ))}
      </CellList>
    </div>
  );
}

function NotifySection() {
  const { api } = useAuth();
  const [maxUserId, setMaxUserId] = useState('');
  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState<{ text: string; ok: boolean } | null>(null);

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
  );
}
