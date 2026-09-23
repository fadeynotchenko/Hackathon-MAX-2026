// Таймауты HTTP-запросов к Bot API.
//
// Голый fetch без таймаута опасен: зависший вызов останавливает и потребитель
// событий, и опрос апдейтов. Но один таймаут на все запросы тоже не годится —
// long polling `GET /updates` по замыслу висит дольше обычного вызова, а SDK
// не считает TimeoutError поводом для повтора и выходит из цикла опроса
// (поймано живьём 2026-09-24: бот замолкал через 20 секунд после старта).
export const API_TIMEOUT_MS = 15_000;
export const POLLING_TIMEOUT_MS = 90_000;

const UPDATES_PATH = '/updates';

type FetchInput = Parameters<typeof fetch>[0];

export function timeoutFor(input: FetchInput): number {
  const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
  return url.includes(UPDATES_PATH) ? POLLING_TIMEOUT_MS : API_TIMEOUT_MS;
}

export function createFetchWithTimeout(base: typeof fetch = fetch): typeof fetch {
  return (input, init) => {
    const timeout = AbortSignal.timeout(timeoutFor(input));
    return base(input, {
      ...init,
      signal: init?.signal ? AbortSignal.any([init.signal, timeout]) : timeout,
    });
  };
}
