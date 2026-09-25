import { describe, expect, it } from 'vitest';

import type { DailyMetrics } from '@/api/client';

import { makeDay, makeMetrics } from './fixtures';
import {
  autofillRows,
  formatMinutes,
  formatMs,
  formatPeriod,
  formatRange,
  formatsTotal,
  funnelRows,
  kindsTotal,
  rejectionRows,
  summarize,
  toBuckets,
} from './metrics';

function daysFrom(start: string, count: number): DailyMetrics[] {
  const first = new Date(`${start}T00:00:00Z`);
  return Array.from({ length: count }, (_, index) => {
    const day = new Date(first.getTime() + index * 86_400_000).toISOString().slice(0, 10);
    return makeDay(day, { users_new: 1 });
  });
}

describe('toBuckets', () => {
  it('keeps one column per day up to two months', () => {
    const result = toBuckets(daysFrom('2026-09-01', 30));
    expect(result.weekly).toBe(false);
    expect(result.items).toHaveLength(30);
    expect(result.items[0]?.label).toBe('1 сент.');
  });

  it('groups longer periods into weeks ending today', () => {
    const result = toBuckets(daysFrom('2026-06-28', 90));
    expect(result.weekly).toBe(true);
    // 90 = 12 полных недель + 6 дней: неполная только первая.
    expect(result.items.map((bucket) => bucket.days.length)).toEqual([6, ...Array(12).fill(7)]);
    expect(result.items.at(-1)?.label).toBe('19–25 сент.');
  });
});

describe('formatting', () => {
  it('prints ranges across months and whole periods', () => {
    expect(formatRange('2026-08-28', '2026-09-03')).toBe('28 авг. – 3 сент.');
    expect(formatRange('2026-09-24', '2026-09-24')).toBe('24 сент.');
    expect(formatPeriod('2026-08-27', '2026-09-25')).toBe('27 авг. – 25 сент. 2026 г.');
  });

  it('prints durations the way people say them, number glued to its unit', () => {
    const text = (value: string) => value.replace(/\u00a0/g, ' ');
    expect(formatMinutes(null)).toBe('—');
    expect(formatMinutes(0.4)).toBe('меньше минуты');
    expect(text(formatMinutes(12.4))).toBe('12 мин');
    expect(text(formatMinutes(125))).toBe('2 ч 5 мин');
    expect(text(formatMinutes(60 * 27))).toBe('1 дн 3 ч');
    expect(text(formatMs(850))).toBe('850 мс');
    expect(text(formatMs(1830))).toBe('1,8 с');
    expect(formatMs(1830)).toContain('\u00a0');
  });
});

const metrics = makeMetrics();

describe('period rows', () => {
  it('sums kinds and formats over the period, biggest first', () => {
    expect(kindsTotal(metrics.daily)).toEqual([
      { key: 'invoice', label: 'Счета', value: 3 },
      { key: 'offer', label: 'КП', value: 1 },
      { key: 'mystery', label: 'Другие', value: 1 },
    ]);
    expect(formatsTotal(metrics.daily).map((row) => [row.label, row.value])).toEqual([
      ['PDF', 2],
      ['DOCX', 1],
    ]);
  });

  it('keeps funnel order and measures each step against created documents', () => {
    const rows = funnelRows(metrics.funnel);
    expect(rows.map((row) => row.key)).toEqual([
      'created',
      'ready',
      'rendered',
      'sent',
      'delivered',
    ]);
    expect(rows[0]?.share).toBe(1);
    expect(rows[3]).toMatchObject({ label: 'Отправлен в чат', value: 2, share: 0.4 });
    expect(funnelRows({ ...metrics.funnel, created: 0 })[1]?.share).toBeNull();
  });

  it('shows filled sources only and keeps manual entry as muted context', () => {
    const rows = autofillRows(metrics.autofill);
    expect(rows.map((row) => row.key)).toEqual(['profile', 'manual', 'counterparty']);
    expect(rows.find((row) => row.key === 'manual')).toMatchObject({ muted: true, share: 0.3 });
    expect(rows.find((row) => row.key === 'profile')?.muted).toBe(false);
  });

  it('names known rejection codes and keeps unknown ones as they are', () => {
    expect(rejectionRows(metrics.rejections)).toEqual([
      { key: 'field.inn_invalid', label: 'ИНН не прошёл проверку', value: 3 },
      { key: 'field.new_code', label: 'field.new_code', value: 1 },
    ]);
  });

  it('takes users and activity from the last day and sums the rest', () => {
    expect(summarize(metrics)).toEqual({
      usersTotal: 42,
      usersNew: 4,
      activeWeek: 9,
      activeToday: 5,
      documentsCreated: 5,
      documentsCopied: 1,
      automaticShare: 0.7,
    });
  });
});
