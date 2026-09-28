import { act, fireEvent, render, screen } from '@testing-library/react';
import { useEffect, useState } from 'react';
import {
  MemoryRouter,
  NavigationType,
  Route,
  Routes,
  useLocation,
  useNavigate,
  type Location,
  type NavigateFunction,
  type NavigateOptions,
} from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  ScreenContext,
  TAB_NAVIGATION,
  nextStack,
  useScreenStack,
  useScreenState,
  useScrollMemory,
} from './screenMemory';
import { useAsync } from './useAsync';

const TABS = ['/a', '/b'];
const router: { navigate?: NavigateFunction } = {};
const mounts: Record<string, number> = {};
let loads = 0;

function go(to: string | number, options?: NavigateOptions): void {
  const navigate = router.navigate!;
  if (typeof to === 'number') void navigate(to);
  else void navigate(to, options);
}

function Screen({ name }: { name: string }) {
  const [query, setQuery] = useScreenState('query', '');
  const data = useAsync(() => Promise.resolve(++loads), []);
  const navigate = useNavigate();
  useEffect(() => {
    router.navigate = navigate;
  }, [navigate]);
  useEffect(() => {
    mounts[name] = (mounts[name] ?? 0) + 1;
  }, [name]);
  return (
    <>
      <input aria-label={name} value={query} onChange={(event) => setQuery(event.target.value)} />
      <span data-testid={`${name}-data`}>{data.loading ? 'loading' : data.data}</span>
    </>
  );
}

function Entry({ location, active }: { location: Location; active: boolean }) {
  const [returns, setReturns] = useState(0);
  const [wasActive, setWasActive] = useState(active);
  if (wasActive !== active) {
    setWasActive(active);
    if (active) setReturns((n) => n + 1);
  }
  return (
    <ScreenContext.Provider value={{ active, returns }}>
      <div hidden={!active}>
        <Routes location={location}>
          <Route path="/a" element={<Screen name="a" />} />
          <Route path="/b" element={<Screen name="b" />} />
          <Route path="/detail" element={<Screen name="detail" />} />
        </Routes>
      </div>
    </ScreenContext.Provider>
  );
}

function Shell() {
  const location = useLocation();
  const stack = useScreenStack();
  useScrollMemory(TABS);
  return stack.map((entry) => (
    <Entry key={entry.key} location={entry} active={entry.key === location.key} />
  ));
}

function scrolledTo(y: number) {
  Object.defineProperty(window, 'scrollY', { value: y, configurable: true });
  fireEvent.scroll(window);
}

function visible(name: string): HTMLElement {
  return screen.getByRole('textbox', { name });
}

async function setup() {
  for (const key of Object.keys(mounts)) delete mounts[key];
  const scrollTo = vi.spyOn(window, 'scrollTo').mockImplementation(() => undefined);
  const first = String(loads + 1);
  render(
    <MemoryRouter initialEntries={['/a']}>
      <Shell />
    </MemoryRouter>,
  );
  await screen.findByText(first);
  return scrollTo;
}

afterEach(() => vi.restoreAllMocks());

describe('screen stack', () => {
  it('returns to the same screen on «back»: no remount, same state and scroll', async () => {
    const scrollTo = await setup();
    fireEvent.change(visible('a'), { target: { value: 'счёт' } });
    scrolledTo(400);

    act(() => go('/detail'));
    expect(visible('detail')).toHaveValue('');
    expect(scrollTo).toHaveBeenLastCalledWith(0, 0);

    const before = loads;
    await act(async () => go(-1));
    expect(visible('a')).toHaveValue('счёт');
    expect(scrollTo).toHaveBeenLastCalledWith(0, 400);
    expect(mounts['a']).toBe(1);
    // Данные обновились тихо: без «loading», сразу новым ответом.
    expect(screen.getByTestId('a-data')).toHaveTextContent(String(before + 1));
  });

  it('keeps a tab as it was left, but not a plain link to the same path', async () => {
    const scrollTo = await setup();
    fireEvent.change(visible('a'), { target: { value: 'договор' } });
    scrolledTo(250);

    act(() => go('/b', { state: TAB_NAVIGATION }));
    act(() => go('/a', { state: TAB_NAVIGATION }));
    expect(visible('a')).toHaveValue('договор');
    expect(scrollTo).toHaveBeenLastCalledWith(0, 250);

    act(() => go('/a'));
    expect(visible('a')).toHaveValue('');
    expect(scrollTo).toHaveBeenLastCalledWith(0, 0);
  });
});

describe('nextStack', () => {
  const at = (key: string, state: unknown = null): Location => ({
    key,
    pathname: `/${key}`,
    search: '',
    hash: '',
    state,
  });
  const keys = (stack: Location[]) => stack.map((entry) => entry.key);

  it('pushes, replaces the top, pops back to a known entry and restarts on tabs', () => {
    const stack = [at('a'), at('b')];
    expect(keys(nextStack(stack, at('c'), NavigationType.Push))).toEqual(['a', 'b', 'c']);
    expect(keys(nextStack(stack, at('c'), NavigationType.Replace))).toEqual(['a', 'c']);
    expect(keys(nextStack(stack, at('a'), NavigationType.Pop))).toEqual(['a']);
    expect(keys(nextStack(stack, at('x'), NavigationType.Pop))).toEqual(['x']);
    expect(keys(nextStack(stack, at('t', TAB_NAVIGATION), NavigationType.Push))).toEqual(['t']);
  });
});
