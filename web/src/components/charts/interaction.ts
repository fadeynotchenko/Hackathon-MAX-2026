// Выбор точки на графике пальцем, мышью и стрелками клавиатуры.
import { useState, type KeyboardEvent, type PointerEvent } from 'react';

import type { TooltipRow } from './parts';

// Текст подсказки для читалки экрана: живой регион есть всегда, меняется текст.
export function describeRows(title: string, rows: TooltipRow[]): string {
  return [title, ...rows.map((row) => `${row.name}: ${row.value}`)].join(', ');
}

// Выбранная точка ряда: палец и мышь выбирают ближайшую по X, стрелки — соседнюю.
// На касании подсказка остаётся после того, как палец убран: её надо успеть прочитать.
export function useActivePoint(count: number, indexAt: (x: number) => number) {
  const [active, setActive] = useState<number | null>(null);
  const clamp = (index: number) => Math.min(count - 1, Math.max(0, index));

  const fromPointer = (event: PointerEvent<SVGSVGElement>) => {
    if (count === 0) return;
    const box = event.currentTarget.getBoundingClientRect();
    setActive(clamp(indexAt(event.clientX - box.left)));
  };

  const onKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (count === 0) return;
    const moves: Record<string, (current: number | null) => number | null> = {
      ArrowRight: (current) => clamp(current === null ? 0 : current + 1),
      ArrowLeft: (current) => clamp(current === null ? count - 1 : current - 1),
      Home: () => 0,
      End: () => count - 1,
      Escape: () => null,
    };
    const move = moves[event.key];
    if (!move) return;
    event.preventDefault();
    setActive(move);
  };

  return {
    active: active === null ? null : clamp(active),
    pointer: {
      onPointerDown: fromPointer,
      onPointerMove: fromPointer,
      onPointerLeave: (event: PointerEvent<SVGSVGElement>) => {
        if (event.pointerType === 'mouse') setActive(null);
      },
    },
    keyboard: {
      onKeyDown,
      onFocus: () => setActive((current) => current ?? (count ? count - 1 : null)),
      onBlur: () => setActive(null),
    },
  };
}
