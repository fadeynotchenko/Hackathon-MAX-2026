// Общие части графиков: карточка с переключателем «таблица», легенда,
// всплывающая подсказка и табличный вид. Цвета — токены MAX UI через
// переменные --chart-* (app.css).
import { Button, Typography } from '@maxhub/max-ui';
import { useState, type ReactNode } from 'react';

export type Tone = 'accent' | 'context';

export interface ChartCardProps {
  title: string;
  subtitle?: ReactNode;
  legend?: ReactNode;
  // Табличный вид того же ряда: доступен без наведения и читалкой экрана.
  table?: ReactNode;
  children: ReactNode;
}

export function ChartCard({ title, subtitle, legend, table, children }: ChartCardProps) {
  const [asTable, setAsTable] = useState(false);
  return (
    <figure className="chart-card">
      <div className="chart-card__head">
        <figcaption className="chart-card__titles">
          <Typography.Text variant="body-strong">{title}</Typography.Text>
          {subtitle ? (
            <Typography.Text variant="description" color="secondary">
              {subtitle}
            </Typography.Text>
          ) : null}
        </figcaption>
        {table ? (
          <Button
            size="xsmall"
            variant="secondary"
            aria-pressed={asTable}
            onClick={() => setAsTable((value) => !value)}
          >
            {asTable ? 'График' : 'Таблица'}
          </Button>
        ) : null}
      </div>
      {asTable ? null : legend}
      {asTable ? table : children}
    </figure>
  );
}

export interface LegendItem {
  key: string;
  label: string;
  tone: Tone;
  shape: 'line' | 'rect';
}

export function Legend({ items }: { items: LegendItem[] }) {
  return (
    <ul className="chart-legend">
      {items.map((item) => (
        <li key={item.key} className="chart-legend__item">
          <span
            className={`chart-key chart-key--${item.shape} chart-key--${item.tone}`}
            aria-hidden="true"
          />
          {item.label}
        </li>
      ))}
    </ul>
  );
}

export function ChartTable({ columns, rows }: { columns: string[]; rows: string[][] }) {
  return (
    <div className="chart-table__scroll">
      <table className="chart-table">
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column} scope="col">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map(([head = '', ...cells]) => (
            <tr key={head}>
              <th scope="row">{head}</th>
              {cells.map((cell, index) => (
                <td key={index}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export interface TooltipRow {
  key: string;
  name: string;
  value: string;
  tone?: Tone;
}

// Значение — главное (жирное), имя ряда — второе: ряд читатель уже видит,
// ему нужно число. Ряд помечен короткой линией его цвета, а не плашкой.
export function ChartTooltip({
  x,
  width,
  title,
  rows,
}: {
  x: number;
  width: number;
  title: string;
  rows: TooltipRow[];
}) {
  const style = x < width / 2 ? { left: x + 10 } : { right: width - x + 10 };
  return (
    <div className="chart-tooltip" style={style} aria-hidden="true">
      <div className="chart-tooltip__title">{title}</div>
      {rows.map((row) => (
        <div key={row.key} className="chart-tooltip__row">
          {row.tone ? (
            <span className={`chart-key chart-key--line chart-key--${row.tone}`} />
          ) : null}
          <span className="chart-tooltip__value">{row.value}</span>
          <span className="chart-tooltip__name">{row.name}</span>
        </div>
      ))}
    </div>
  );
}
