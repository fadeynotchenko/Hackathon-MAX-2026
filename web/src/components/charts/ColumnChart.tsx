// Столбцы одного ряда по дням или неделям: не толще 24px, скругление 4px только
// у вершины, зазор между соседями. Подписан один столбец — максимум; остальные
// значения — в подсказке и таблице.
import { formatNumber } from '@/lib/format';

import { describeRows, useActivePoint } from './interaction';
import { ChartTooltip, type TooltipRow } from './parts';
import { niceScale } from './scale';
import { useWidth } from './useWidth';

export interface Column {
  key: string;
  label: string;
  value: number;
  // Разбивка столбца для подсказки: «из них на основе прошлых», виды документов.
  details?: TooltipRow[];
}

const HEIGHT = 176;
const TOP = 20;
const AXIS = 24;
const CHAR = 7;
const GAP = 2;
const MAX_BAR = 24;
const RADIUS = 4;

const crisp = (value: number) => Math.round(value) + 0.5;

// Прямоугольник с радиусом только у вершины: столбец растёт от оси.
function columnPath(x: number, top: number, width: number, bottom: number): string {
  const r = Math.min(RADIUS, width / 2, bottom - top);
  return [
    `M${x},${bottom}`,
    `L${x},${top + r}`,
    `Q${x},${top} ${x + r},${top}`,
    `L${x + width - r},${top}`,
    `Q${x + width},${top} ${x + width},${top + r}`,
    `L${x + width},${bottom}`,
    'Z',
  ].join(' ');
}

export function ColumnChart({
  columns,
  name,
  label,
  format = formatNumber,
}: {
  columns: Column[];
  // Имя ряда в подсказке: «Создано», «Новых».
  name: string;
  label: string;
  format?: (value: number) => string;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const count = columns.length;
  const values = columns.map((column) => column.value);
  const max = Math.max(0, ...values);
  const scale = niceScale(max);
  const plotHeight = HEIGHT - TOP - AXIS;
  const bottom = TOP + plotHeight;
  const y = (value: number) => TOP + plotHeight * (1 - value / scale.max);
  const left = Math.max(...scale.ticks.map((tick) => format(tick).length)) * CHAR + 10;
  const plotWidth = Math.max(10, width - left - 8);
  const slot = count ? plotWidth / count : plotWidth;
  const barWidth = Math.max(1, Math.min(MAX_BAR, slot - GAP));
  const center = (index: number) => left + slot * index + slot / 2;
  const { active, pointer, keyboard } = useActivePoint(count, (px) =>
    Math.floor((px - left) / slot),
  );
  // Подпись у самого высокого столбца (последнего из равных — ближе к «сегодня»).
  const peak = max > 0 ? values.lastIndexOf(max) : -1;

  const current = active === null ? null : columns[active];
  const rows: TooltipRow[] = current
    ? [
        { key: 'value', name, value: format(current.value), tone: 'accent' },
        ...(current.details ?? []),
      ]
    : [];

  return (
    <div ref={ref} className="chart" role="group" aria-label={label} tabIndex={0} {...keyboard}>
      <svg className="chart__svg" width={width} height={HEIGHT} aria-hidden="true" {...pointer}>
        {scale.ticks.map((tick) => (
          <g key={tick}>
            <line
              className={tick === 0 ? 'chart__baseline' : 'chart__grid'}
              x1={left}
              x2={left + plotWidth}
              y1={crisp(y(tick))}
              y2={crisp(y(tick))}
            />
            <text className="chart__tick" x={left - 6} y={y(tick)} dy="0.32em" textAnchor="end">
              {format(tick)}
            </text>
          </g>
        ))}
        {columns.map((column, index) =>
          column.value > 0 ? (
            <path
              key={column.key}
              className={
                active !== null && active !== index ? 'chart__bar chart__bar--dim' : 'chart__bar'
              }
              d={columnPath(center(index) - barWidth / 2, y(column.value), barWidth, bottom)}
            />
          ) : null,
        )}
        {peak >= 0 && active === null ? (
          <text className="chart__label" x={center(peak)} y={y(max) - 6} textAnchor="middle">
            {format(max)}
          </text>
        ) : null}
        {count > 0 ? (
          <>
            <text
              className="chart__tick"
              x={count > 1 ? left : center(0)}
              y={HEIGHT - 6}
              textAnchor={count > 1 ? 'start' : 'middle'}
            >
              {columns[0]?.label}
            </text>
            {count > 1 ? (
              <text className="chart__tick" x={left + plotWidth} y={HEIGHT - 6} textAnchor="end">
                {columns[count - 1]?.label}
              </text>
            ) : null}
          </>
        ) : null}
      </svg>
      {current && active !== null ? (
        <ChartTooltip x={center(active)} width={width} title={current.label} rows={rows} />
      ) : null}
      <div className="visually-hidden" aria-live="polite">
        {current ? describeRows(current.label, rows) : ''}
      </div>
    </div>
  );
}
