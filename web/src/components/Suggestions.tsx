// Подсказки под полем ввода: человек набирает название, ИНН, БИК или адрес —
// под полем появляется список из реестра, выбор заполняет поле и соседние.
// Запрос уходит только на набор с клавиатуры (подстановка из подсказки или с
// фото список не открывает) и после паузы в наборе: иначе каждое нажатие клавиши
// тратило бы дневной лимит ключа. Ответ на устаревший набор отбрасывается.
//
// Список — листбокс у поля-комбобокса: стрелки и Enter выбирают, Escape и
// уход из поля закрывают. Касание по строке не уводит фокус из поля, иначе
// список закрылся бы раньше, чем выбор дошёл до формы.
import { Spinner, Typography } from '@maxhub/max-ui';
import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react';

import type { RequisiteSuggestion } from '@/api/client';
import { ApiError } from '@/api/client';
import { MIN_SUGGEST_QUERY, markSuggestUnavailable, suggestUnavailable } from '@/lib/suggest';

const DEBOUNCE_MS = 350;

export interface SuggestSource {
  fetch: (query: string) => Promise<RequisiteSuggestion[]>;
  onPick: (suggestion: RequisiteSuggestion) => void;
  // Подпись над списком: «Из ЕГРЮЛ», «Справочник банков».
  title: string;
}

export function useSuggestions(source: SuggestSource | undefined) {
  const listId = useId();
  const [items, setItems] = useState<RequisiteSuggestion[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  // Набор с клавиатуры: последний запрос побеждает, ответы на прежние отбрасываются.
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const ticket = useRef(0);

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );

  const cancel = () => {
    ticket.current += 1;
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
  };

  const close = () => {
    setOpen(false);
    setActive(-1);
  };

  const pick = (suggestion: RequisiteSuggestion) => {
    cancel();
    close();
    setItems([]);
    setLoading(false);
    source?.onPick(suggestion);
  };

  const shown = open && Boolean(source) && (items.length > 0 || loading);

  const onKeyDown = (event: KeyboardEvent) => {
    if (!shown) return;
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      const step = event.key === 'ArrowDown' ? 1 : -1;
      setActive((prev) => (prev + step + items.length) % Math.max(items.length, 1));
    } else if (event.key === 'Enter' && active >= 0 && items[active]) {
      event.preventDefault();
      pick(items[active]);
    } else if (event.key === 'Escape') {
      event.preventDefault();
      close();
    }
  };

  const inputProps = source
    ? {
        role: 'combobox' as const,
        autoComplete: 'off',
        'aria-autocomplete': 'list' as const,
        'aria-expanded': shown,
        'aria-controls': listId,
        ...(shown && active >= 0 ? { 'aria-activedescendant': `${listId}-${active}` } : {}),
        onKeyDown,
      }
    : {};

  const onType = (value: string) => {
    if (!source) return;
    cancel();
    setOpen(true);
    const text = value.trim();
    if (text.length < MIN_SUGGEST_QUERY || suggestUnavailable()) {
      setItems([]);
      setLoading(false);
      return;
    }
    const mine = ticket.current;
    const { fetch } = source;
    setLoading(true);
    timer.current = setTimeout(() => {
      fetch(text)
        .then((found) => {
          if (mine !== ticket.current) return;
          setItems(found);
          setActive(-1);
        })
        .catch((err: unknown) => {
          if (err instanceof ApiError && err.status === 503) markSuggestUnavailable();
          if (mine === ticket.current) setItems([]);
        })
        .finally(() => {
          if (mine === ticket.current) setLoading(false);
        });
    }, DEBOUNCE_MS);
  };

  const list = shown ? (
    <div className="suggest">
      <div className="suggest__head">
        <Typography.Text variant="description" color="tertiary">
          {source?.title}
        </Typography.Text>
        {loading ? <Spinner size={16} appearance="themed" /> : null}
      </div>
      <ul id={listId} role="listbox" aria-label={source?.title} className="suggest__list">
        {items.map((item, index) => (
          <li
            key={`${item.title}-${item.subtitle}`}
            id={`${listId}-${index}`}
            role="option"
            aria-selected={index === active}
            className={`suggest__item${index === active ? ' suggest__item--active' : ''}`}
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => pick(item)}
          >
            <Typography.Text variant="body" className="suggest__title">
              {item.title}
            </Typography.Text>
            {item.subtitle ? (
              <Typography.Text variant="description" color="secondary">
                {item.subtitle}
              </Typography.Text>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  ) : null;

  // Закрытие списка на blur отдаётся отдельно: поле само решает, что ещё делать
  // при уходе с него (проверка реквизита).
  return { inputProps, onType, list, close: source ? close : undefined };
}
