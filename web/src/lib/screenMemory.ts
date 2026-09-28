// Память экранов. Экраны живут стеком, как в нативной навигации: переход
// вперёд кладёт новый экран поверх, прежний остаётся смонтированным и скрытым,
// «Назад» снимает верхний и показывает нижний таким, каким его оставили, без
// перезагрузки. Прокрутка и локальное состояние (поиск, фильтр) привязаны к
// записи истории: вкладка таб-бара открывается такой, какой её оставили, хотя
// стек при переходе по вкладке начинается заново. Новый экран — всегда сверху.
// BrowserRouter не умеет ScrollRestoration (она есть только у data-router), а
// экран, открытый по вкладке, грузит данные заново, поэтому прокрутка догоняет
// высоту содержимого, пока оно не дорастёт.
import {
  createContext,
  useContext,
  useLayoutEffect,
  useState,
  type Dispatch,
  type SetStateAction,
} from 'react';
import { NavigationType, useLocation, useNavigationType, type Location } from 'react-router-dom';

interface ScreenRecord {
  scroll: number;
  state: Map<string, unknown>;
}

// Состояние перехода по таб-бару: по нему вкладка отличается от «Создать ещё»,
// которое ведёт на тот же адрес, но как на новый экран.
export const TAB_NAVIGATION = { tab: true } as const;

const RESTORE_TIMEOUT_MS = 1500;

export interface ScreenActivity {
  // Экран сверху стека: только он слушает системную «Назад».
  active: boolean;
  // Сколько раз на экран вернулись; смена — повод тихо обновить данные,
  // которые мог поменять экран выше.
  returns: number;
}

export const ScreenContext = createContext<ScreenActivity>({ active: true, returns: 0 });

export function useScreenActivity(): ScreenActivity {
  return useContext(ScreenContext);
}

const records = new Map<string, ScreenRecord>();
const lastTabEntry = new Map<string, string>();

function isTabNavigation(location: Location): boolean {
  const state: unknown = location.state;
  return typeof state === 'object' && state !== null && 'tab' in state;
}

// Вызывается при рендере, поэтому идемпотентна: повторный рендер StrictMode
// получает ту же запись.
function recordFor(location: Location): ScreenRecord {
  const existing = records.get(location.key);
  if (existing) return existing;
  const tabSource = isTabNavigation(location) ? lastTabEntry.get(location.pathname) : undefined;
  const source = tabSource ? records.get(tabSource) : undefined;
  const record: ScreenRecord = source
    ? { scroll: source.scroll, state: new Map(source.state) }
    : { scroll: 0, state: new Map() };
  records.set(location.key, record);
  return record;
}

export function nextStack(
  stack: readonly Location[],
  location: Location,
  type: NavigationType,
): Location[] {
  if (isTabNavigation(location)) return [location];
  if (type === NavigationType.Push) return [...stack, location];
  if (type === NavigationType.Replace) return [...stack.slice(0, -1), location];
  // «Назад» к экрану из стека снимает всё, что выше. Записи нет (вперёд
  // кнопкой браузера, перезагрузка) — экран открывается заново.
  const index = stack.findIndex((entry) => entry.key === location.key);
  return index >= 0 ? stack.slice(0, index + 1) : [location];
}

// Подключается один раз в корне приложения; экраны рендерятся по записям стека.
export function useScreenStack(): Location[] {
  const location = useLocation();
  const type = useNavigationType();
  const [stack, setStack] = useState<Location[]>([location]);
  const [seen, setSeen] = useState(location.key);
  if (seen === location.key) return stack;
  const next = nextStack(stack, location, type);
  setSeen(location.key);
  setStack(next);
  return next;
}

export function useScreenState<T>(name: string, initial: T): [T, Dispatch<SetStateAction<T>>] {
  const record = recordFor(useLocation());
  const [value, setValue] = useState<T>(() =>
    record.state.has(name) ? (record.state.get(name) as T) : initial,
  );
  const set: Dispatch<SetStateAction<T>> = (next) => {
    setValue((prev) => {
      const resolved = typeof next === 'function' ? (next as (p: T) => T)(prev) : next;
      record.state.set(name, resolved);
      return resolved;
    });
  };
  return [value, set];
}

// Подключается один раз в корне приложения.
export function useScrollMemory(tabPaths: readonly string[]): void {
  const location = useLocation();
  const navigationType = useNavigationType();

  useLayoutEffect(() => {
    if ('scrollRestoration' in window.history) window.history.scrollRestoration = 'manual';
  }, []);

  // Layout-эффект: запись текущего экрана меняется до того, как браузер
  // пришлёт scroll от укоротившейся страницы, и старая позиция не затирается.
  useLayoutEffect(() => {
    const record = recordFor(location);
    if (tabPaths.includes(location.pathname)) lastTabEntry.set(location.pathname, location.key);

    const restore = navigationType === NavigationType.Pop || isTabNavigation(location);
    const target = restore ? record.scroll : 0;
    let frame = 0;
    let cancelled = false;
    const deadline = performance.now() + RESTORE_TIMEOUT_MS;

    const stop = () => {
      cancelled = true;
      cancelAnimationFrame(frame);
    };
    const attempt = () => {
      if (cancelled) return;
      window.scrollTo(0, target);
      const reachable = document.documentElement.scrollHeight - window.innerHeight;
      if (reachable < target && performance.now() < deadline) {
        frame = requestAnimationFrame(attempt);
      }
    };
    const onScroll = () => {
      record.scroll = window.scrollY;
    };

    attempt();
    window.addEventListener('scroll', onScroll, { passive: true });
    // Палец или колесо пользователя важнее догоняющей прокрутки.
    window.addEventListener('touchstart', stop, { passive: true });
    window.addEventListener('wheel', stop, { passive: true });
    return () => {
      stop();
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('touchstart', stop);
      window.removeEventListener('wheel', stop);
    };
    // Экран определяется ключом записи истории; остальные поля location с ним согласованы.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.key, navigationType]);
}
