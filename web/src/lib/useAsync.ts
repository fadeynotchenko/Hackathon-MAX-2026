// Загрузка данных экрана: состояние, ошибка, повтор. Ответ помнит, для каких
// зависимостей он получен: устаревший (экран ушёл, зависимости сменились)
// отбрасывается, а «загружается» — это «для текущих зависимостей ответа ещё нет».
import { useCallback, useEffect, useState, type DependencyList } from 'react';

import { ApiError } from '@/api/client';

export interface AsyncState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
  setData: (data: T) => void;
}

export function errorText(err: unknown, fallback = 'Не удалось загрузить данные'): string {
  return err instanceof ApiError ? err.message : fallback;
}

interface Settled<T> {
  key: readonly unknown[];
  data: T | null;
  error: string | null;
}

function sameKey(a: readonly unknown[], b: readonly unknown[]): boolean {
  return a.length === b.length && a.every((item, index) => Object.is(item, b[index]));
}

export function useAsync<T>(load: () => Promise<T>, deps: DependencyList): AsyncState<T> {
  const [attempt, setAttempt] = useState(0);
  // Ключ запроса: зависимости вызывающего и номер повтора.
  const key = [...deps, attempt];
  const [settled, setSettled] = useState<Settled<T> | null>(null);

  useEffect(() => {
    let cancelled = false;
    load().then(
      (data) => {
        if (!cancelled) setSettled({ key, data, error: null });
      },
      (err: unknown) => {
        if (!cancelled) setSettled({ key, data: null, error: errorText(err) });
      },
    );
    return () => {
      cancelled = true;
    };
    // load и key пересоздаются на каждый рендер; перезапуск задают их элементы.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, key);

  const reload = useCallback(() => setAttempt((n) => n + 1), []);
  const setData = (data: T) => setSettled({ key, data, error: null });
  const current = settled && sameKey(settled.key, key) ? settled : null;
  return {
    data: current?.data ?? null,
    error: current?.error ?? null,
    loading: current === null,
    reload,
    setData,
  };
}
