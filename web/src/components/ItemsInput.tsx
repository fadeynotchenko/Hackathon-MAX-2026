// Позиции счёта в форме: строка на позицию — наименование, количество,
// единица и цена, у каждой своя сумма, внизу итог. Значение поля — JSON-строка
// (lib/items.ts), которую сервер проверит и пересчитает сам; итог здесь только
// для глаз, чтобы ошибку в цене было видно до сборки файла.
//
// Строки живут в состоянии компонента: пустая строка, которую только что
// добавили, в значение не попадает, и перечитывание значения стёрло бы её.
// Поэтому снаружи строки перечитываются, только когда значение пришло не от
// этого поля (демо-данные, ответ сервера).
import { Input, Typography } from '@maxhub/max-ui';
import { useEffect, useId, useRef, useState } from 'react';

import { IconPlus, IconTrash } from '@/components/icons';
import { formatMoney, pluralize } from '@/lib/format';
import { EMPTY_ROW, itemsTotal, parseItems, rowAmount, serializeItems } from '@/lib/items';
import type { ItemRow } from '@/lib/items';

import '@/styles/items.css';

export interface ItemsInputProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  hint?: string | undefined;
  error?: string | null | undefined;
  source?: { label: string; draft: boolean } | null | undefined;
}

// «10500.00» с сервера читается хуже «10500»: копейки показываем, только если они есть.
function plain(number: string): string {
  return number.replace(/[.,]00$/, '');
}

function rowsOf(value: string): ItemRow[] {
  const rows = parseItems(value).map((row) => ({
    ...row,
    quantity: plain(row.quantity),
    price: plain(row.price),
  }));
  return rows.length > 0 ? rows : [{ ...EMPTY_ROW }];
}

function money(amount: number): string {
  return `${formatMoney(amount.toFixed(2))} ₽`;
}

export function ItemsInput({ label, value, onChange, hint, error, source }: ItemsInputProps) {
  const id = useId();
  const [rows, setRows] = useState<ItemRow[]>(() => rowsOf(value));
  const emitted = useRef(value);

  useEffect(() => {
    if (value === emitted.current) return;
    emitted.current = value;
    setRows(rowsOf(value));
  }, [value]);

  const update = (next: ItemRow[]) => {
    setRows(next);
    const serialized = serializeItems(next);
    emitted.current = serialized;
    onChange(serialized);
  };
  const edit = (index: number, patch: Partial<ItemRow>) =>
    update(rows.map((row, at) => (at === index ? { ...row, ...patch } : row)));
  const remove = (index: number) => {
    const next = rows.filter((_, at) => at !== index);
    update(next.length > 0 ? next : [{ ...EMPTY_ROW }]);
  };

  const total = itemsTotal(rows);
  const counted = rows.filter((row) => rowAmount(row) !== null).length;
  const describedBy = error || hint ? `${id}-note` : undefined;

  return (
    <div className={`field field--multiline items${error ? ' field--error' : ''}`}>
      <div className="field__label">
        <Typography.Text variant="description-strong" color="secondary" asChild>
          <span id={`${id}-label`}>{label}</span>
        </Typography.Text>
        {source ? (
          <Typography.Text
            variant="description"
            className={`source-tag${source.draft ? ' source-tag--draft' : ''}`}
          >
            {source.label}
          </Typography.Text>
        ) : null}
      </div>
      <ol className="items__list" aria-labelledby={`${id}-label`} aria-describedby={describedBy}>
        {rows.map((row, index) => {
          const amount = rowAmount(row);
          const number = index + 1;
          return (
            <li key={index} className="items__row">
              <div className="items__head">
                <Typography.Text variant="description-strong" color="secondary">
                  Позиция {number}
                </Typography.Text>
                <button
                  type="button"
                  className="items__remove"
                  aria-label={`Удалить позицию ${number}`}
                  onClick={() => remove(index)}
                >
                  <IconTrash size={20} />
                </button>
              </div>
              <Input
                className="field__box"
                aria-label={`Наименование, позиция ${number}`}
                placeholder="Что продаёте: товар или услуга"
                value={row.name}
                onChange={(event) => edit(index, { name: event.target.value })}
              />
              <div className="items__numbers">
                <label className="items__cell">
                  <Typography.Text variant="description" color="tertiary">
                    Кол-во
                  </Typography.Text>
                  <Input
                    className="field__box"
                    aria-label={`Количество, позиция ${number}`}
                    placeholder="1"
                    inputMode="decimal"
                    value={row.quantity}
                    onChange={(event) => edit(index, { quantity: event.target.value })}
                  />
                </label>
                <label className="items__cell">
                  <Typography.Text variant="description" color="tertiary">
                    Ед.
                  </Typography.Text>
                  <Input
                    className="field__box"
                    aria-label={`Единица, позиция ${number}`}
                    placeholder="шт."
                    maxLength={20}
                    value={row.unit}
                    onChange={(event) => edit(index, { unit: event.target.value })}
                  />
                </label>
                <label className="items__cell">
                  <Typography.Text variant="description" color="tertiary">
                    Цена, ₽
                  </Typography.Text>
                  <Input
                    className="field__box"
                    aria-label={`Цена, позиция ${number}`}
                    placeholder="0"
                    inputMode="decimal"
                    value={row.price}
                    onChange={(event) => edit(index, { price: event.target.value })}
                  />
                </label>
              </div>
              {amount !== null ? (
                <div className="items__amount">
                  <Typography.Text variant="description" color="tertiary">
                    Сумма
                  </Typography.Text>
                  <Typography.Text variant="body-strong">{money(amount)}</Typography.Text>
                </div>
              ) : null}
            </li>
          );
        })}
      </ol>
      <button
        type="button"
        className="items__add"
        onClick={() => update([...rows, { ...EMPTY_ROW }])}
      >
        <IconPlus size={20} />
        Добавить позицию
      </button>
      {counted > 0 ? (
        <div className="items__total" aria-live="polite">
          <Typography.Text variant="body" color="secondary">
            Итого · {rows.length} {pluralize(rows.length, 'позиция', 'позиции', 'позиций')}
          </Typography.Text>
          <Typography.Text variant="title">{money(total)}</Typography.Text>
        </div>
      ) : null}
      {error ? (
        <Typography.Text
          id={describedBy}
          variant="description"
          className="field__note field__error"
        >
          {error}
        </Typography.Text>
      ) : hint ? (
        <Typography.Text
          id={describedBy}
          variant="description"
          color="tertiary"
          className="field__note"
        >
          {hint}
        </Typography.Text>
      ) : null}
    </div>
  );
}
