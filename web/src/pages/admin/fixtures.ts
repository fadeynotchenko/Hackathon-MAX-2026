// Ответ /admin/metrics для тестов экрана и расчётов.
import type { AdminMetrics, DailyMetrics } from '@/api/client';

export function makeDay(day: string, overrides: Partial<DailyMetrics> = {}): DailyMetrics {
  return {
    day,
    users_total: 10,
    users_new: 0,
    active_day: 0,
    active_week: 0,
    documents_created: 0,
    documents_copied: 0,
    created_by_kind: {},
    rendered_docx: 0,
    rendered_pdf: 0,
    sent: 0,
    delivered: 0,
    delivery_failed: 0,
    rejected: 0,
    ...overrides,
  };
}

export function makeMetrics(overrides: Partial<AdminMetrics> = {}): AdminMetrics {
  return {
    since: '2026-09-24',
    until: '2026-09-25',
    daily: [
      makeDay('2026-09-24', {
        users_total: 40,
        users_new: 2,
        documents_created: 3,
        created_by_kind: { invoice: 2, offer: 1 },
        rendered_pdf: 2,
      }),
      makeDay('2026-09-25', {
        users_total: 42,
        users_new: 2,
        active_day: 5,
        active_week: 9,
        documents_created: 2,
        documents_copied: 1,
        created_by_kind: { invoice: 1, mystery: 1 },
        rendered_docx: 1,
      }),
    ],
    funnel: { created: 5, ready: 4, rendered: 3, sent: 2, delivered: 2 },
    autofill: {
      by_source: { manual: 6, profile: 10, counterparty: 4, ocr: 0, agent: 0, default: 0 },
      total: 20,
      automatic_share: 0.7,
    },
    rejections: { 'field.inn_invalid': 3, 'field.new_code': 1 },
    deliveries: { delivered: 2, failed: 0, pending: 0 },
    time_to_send_minutes: { count: 2, median: 12, p90: 30 },
    render_ms: { pdf: { count: 2, median: 1800, p90: 2500 } },
    ...overrides,
  };
}
