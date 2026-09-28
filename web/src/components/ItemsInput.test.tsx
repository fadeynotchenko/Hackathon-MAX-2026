import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { FieldInput } from './FieldInput';

function Harness({ initial, spy }: { initial: string; spy: (value: string) => void }) {
  const [value, setValue] = useState(initial);
  return (
    <FieldInput
      label="Позиции"
      type="items"
      value={value}
      onChange={(next) => {
        spy(next);
        setValue(next);
      }}
    />
  );
}

const ONE = JSON.stringify([{ name: 'Сайт', quantity: '1', unit: 'усл.', price: '120000.00' }]);

describe('ItemsInput', () => {
  it('renders the items field as rows and keeps a new empty row while typing', () => {
    const spy = vi.fn();
    render(<Harness initial={ONE} spy={spy} />);
    expect(screen.getByLabelText('Наименование, позиция 1')).toHaveValue('Сайт');

    fireEvent.click(screen.getByRole('button', { name: 'Добавить позицию' }));
    // Пустая строка в значение не попадает, но из формы не пропадает.
    expect(screen.getByLabelText('Наименование, позиция 2')).toHaveValue('');
    expect(JSON.parse(spy.mock.lastCall?.[0] as string)).toHaveLength(1);

    fireEvent.change(screen.getByLabelText('Наименование, позиция 2'), {
      target: { value: 'Хостинг' },
    });
    fireEvent.change(screen.getByLabelText('Количество, позиция 2'), { target: { value: '3' } });
    fireEvent.change(screen.getByLabelText('Цена, позиция 2'), { target: { value: '1 000' } });
    expect(JSON.parse(spy.mock.lastCall?.[0] as string)).toEqual([
      // Цену «120000.00» с сервера поле показывает без пустых копеек.
      { name: 'Сайт', quantity: '1', unit: 'усл.', price: '120000' },
      { name: 'Хостинг', quantity: '3', unit: '', price: '1 000' },
    ]);
    expect(screen.getByText('3 000 ₽')).toBeInTheDocument();
    expect(screen.getByText('Итого · 2 позиции')).toBeInTheDocument();
    expect(screen.getByText('123 000 ₽')).toBeInTheDocument();
  });

  it('removes a row, and removing the last one leaves an empty row and an empty value', () => {
    const spy = vi.fn();
    render(<Harness initial={ONE} spy={spy} />);
    fireEvent.click(screen.getByRole('button', { name: 'Удалить позицию 1' }));
    expect(spy).toHaveBeenLastCalledWith('');
    expect(screen.getByLabelText('Наименование, позиция 1')).toHaveValue('');
    expect(screen.queryByText(/Итого/)).toBeNull();
  });

  it('rereads rows when the value comes from outside (demo data, server answer)', () => {
    const { rerender } = render(
      <FieldInput label="Позиции" type="items" value="" onChange={() => undefined} />,
    );
    expect(screen.getByLabelText('Наименование, позиция 1')).toHaveValue('');
    rerender(<FieldInput label="Позиции" type="items" value={ONE} onChange={() => undefined} />);
    expect(screen.getByLabelText('Наименование, позиция 1')).toHaveValue('Сайт');
  });

  it('shows the server error under the table', () => {
    render(
      <FieldInput
        label="Позиции"
        type="items"
        value={ONE}
        error="укажите цену позиции 2"
        onChange={() => undefined}
      />,
    );
    expect(screen.getByText('укажите цену позиции 2')).toBeInTheDocument();
  });
});
