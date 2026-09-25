// Горизонтальные полосы с подписью и значением у каждой: для итогов периода
// (виды документов, воронка, источники значений, ошибки). Значение подписано
// всегда, поэтому подсказка не нужна — список сам себе табличный вид.
import { formatNumber } from '@/lib/format';

export interface BarRow {
  key: string;
  label: string;
  value: number;
  // Вторая часть подписи: доля, «из созданных».
  note?: string;
  // Контекст (ручной ввод рядом с автозаполнением): серым, а не акцентом.
  muted?: boolean;
}

// Воронка упорядочена: шаги — ступени одного цвета, от акцента к насыщенному.
// Пять ступеней --chart-step-0…4 проверены на контраст в обеих темах.
const STEPS = 5;

export function BarList({
  rows,
  label,
  ordinal = false,
  format = formatNumber,
}: {
  rows: BarRow[];
  label: string;
  ordinal?: boolean;
  format?: (value: number) => string;
}) {
  const max = Math.max(0, ...rows.map((row) => row.value));
  return (
    <ul className="bar-list" aria-label={label}>
      {rows.map((row, index) => {
        const tone = ordinal
          ? `step-${Math.min(index, STEPS - 1)}`
          : row.muted
            ? 'context'
            : 'accent';
        const width = max > 0 && row.value > 0 ? `max(2px, ${(row.value / max) * 100}%)` : '0';
        return (
          <li key={row.key} className="bar-row">
            <div className="bar-row__text">
              <span className="bar-row__label">{row.label}</span>
              <span className="bar-row__value">
                {format(row.value)}
                {row.note ? <span className="bar-row__note"> · {row.note}</span> : null}
              </span>
            </div>
            <div className="bar-row__track" aria-hidden="true">
              <div className={`bar-row__bar bar-row__bar--${tone}`} style={{ width }} />
            </div>
          </li>
        );
      })}
    </ul>
  );
}
