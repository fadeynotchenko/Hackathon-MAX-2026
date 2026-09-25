// Шкала оси Y: круглые деления 0 / 5 / 10, а не 0 / 3,7 / 7,4. Все ряды
// админки — счётчики, поэтому шаг не меньше единицы.
export interface Scale {
  max: number;
  ticks: number[];
}

export function niceScale(max: number, count = 3): Scale {
  if (!(max > 0)) return { max: 1, ticks: [0, 1] };
  const raw = max / count;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const step = Math.max(1, [1, 2, 5, 10].map((m) => m * magnitude).find((s) => s >= raw) ?? raw);
  const top = Math.ceil(max / step) * step;
  const ticks: number[] = [];
  for (let tick = 0; tick <= top + step / 2; tick += step) ticks.push(tick);
  return { max: top, ticks };
}
