// Линии по дням: 2px, круглые стыки, значение в конце линии, перекрестие с
// подсказкой по всем рядам в выбранный день. Одна ось Y: ряды одной природы.
import { formatNumber } from '@/lib/format';

import { describeRows, useActivePoint } from './interaction';
import { ChartTooltip, type Tone, type TooltipRow } from './parts';
import { niceScale } from './scale';
import { useWidth } from './useWidth';

export interface LineSeries {
  key: string;
  name: string;
  tone: Tone;
  values: number[];
}

const HEIGHT = 180;
const TOP = 12;
const AXIS = 24;
const CHAR = 7;
// Подписи концов линий ближе этого по вертикали налезают друг на друга:
// тогда их нет вовсе, значения — в легенде, подсказке и таблице.
const LABEL_GAP = 14;

const crisp = (value: number) => Math.round(value) + 0.5;

export function LineChart({
  labels,
  series,
  label,
  format = formatNumber,
}: {
  labels: string[];
  series: LineSeries[];
  label: string;
  format?: (value: number) => string;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const count = labels.length;
  const scale = niceScale(Math.max(0, ...series.flatMap((line) => line.values)));
  const plotHeight = HEIGHT - TOP - AXIS;
  const y = (value: number) => TOP + plotHeight * (1 - value / scale.max);

  const ends = series.map((line) => line.values[count - 1] ?? 0);
  const endYs = ends.map(y);
  const showEnds =
    count > 0 &&
    endYs.every((a, i) => endYs.every((b, j) => i === j || Math.abs(a - b) >= LABEL_GAP));
  const left = Math.max(...scale.ticks.map((tick) => format(tick).length)) * CHAR + 10;
  const right = showEnds ? Math.max(...ends.map((value) => format(value).length)) * CHAR + 14 : 8;
  const plotWidth = Math.max(10, width - left - right);
  const x = (index: number) =>
    count <= 1 ? left + plotWidth / 2 : left + (index * plotWidth) / (count - 1);
  const indexAt = (px: number) =>
    count <= 1 ? 0 : Math.round(((px - left) / plotWidth) * (count - 1));
  const { active, pointer, keyboard } = useActivePoint(count, indexAt);

  // Контекст рисуется первым, акцент — поверх него.
  const ordered = [...series].sort(
    (a, b) => Number(a.tone === 'accent') - Number(b.tone === 'accent'),
  );
  const title = active === null ? '' : (labels[active] ?? '');
  const rows: TooltipRow[] =
    active === null
      ? []
      : series.map((line) => ({
          key: line.key,
          name: line.name,
          value: format(line.values[active] ?? 0),
          tone: line.tone,
        }));

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
        {count > 0 ? (
          <>
            <text
              className="chart__tick"
              x={x(0)}
              y={HEIGHT - 6}
              textAnchor={count > 1 ? 'start' : 'middle'}
            >
              {labels[0]}
            </text>
            {count > 1 ? (
              <text className="chart__tick" x={x(count - 1)} y={HEIGHT - 6} textAnchor="end">
                {labels[count - 1]}
              </text>
            ) : null}
          </>
        ) : null}
        {ordered.map((line) => (
          <path
            key={line.key}
            className={`chart__line chart__line--${line.tone}`}
            d={line.values
              .map((value, index) => `${index ? 'L' : 'M'}${x(index)},${y(value)}`)
              .join(' ')}
          />
        ))}
        {active !== null ? (
          <line
            className="chart__crosshair"
            x1={crisp(x(active))}
            x2={crisp(x(active))}
            y1={TOP}
            y2={TOP + plotHeight}
          />
        ) : null}
        {ordered.map((line) => {
          const index = active ?? count - 1;
          if (count === 0) return null;
          return (
            <circle
              key={line.key}
              className={`chart__dot chart__dot--${line.tone}`}
              cx={x(index)}
              cy={y(line.values[index] ?? 0)}
              r={4}
            />
          );
        })}
        {showEnds && active === null
          ? series.map((line, index) => (
              <text
                key={line.key}
                className="chart__label"
                x={x(count - 1) + 8}
                y={endYs[index]}
                dy="0.32em"
              >
                {format(ends[index] ?? 0)}
              </text>
            ))
          : null}
      </svg>
      {active !== null ? (
        <ChartTooltip x={x(active)} width={width} title={title} rows={rows} />
      ) : null}
      <div className="visually-hidden" aria-live="polite">
        {active !== null ? describeRows(title, rows) : ''}
      </div>
    </div>
  );
}
