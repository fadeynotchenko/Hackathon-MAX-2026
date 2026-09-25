// Ширина контейнера графика: SVG рисуется в настоящих пикселях, чтобы линии в
// 2px и подписи не растягивались вместе с viewBox на широком экране.
import { useLayoutEffect, useRef, useState } from 'react';

export function useWidth<T extends HTMLElement>(fallback = 320) {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(fallback);
  useLayoutEffect(() => {
    const element = ref.current;
    if (!element) return;
    // jsdom и первый кадр до раскладки дают 0: остаёмся на запасной ширине.
    const measure = () => setWidth(element.clientWidth || fallback);
    measure();
    if (typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [fallback]);
  return [ref, width] as const;
}
