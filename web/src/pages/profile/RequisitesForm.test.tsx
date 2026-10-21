// Стенд вне MAX: кнопка «Тестовые реквизиты» подставляет сходящийся набор своей
// стороны — ИНН, БИК и счета проходят проверку, руками их не подобрать.
// Поиск по реестру: ИНН в поле открывает список, выбор заполняет юрданные.
import { fireEvent, screen, waitFor } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { mockApi, renderScreen } from '@/test-utils';

import { RequisitesForm } from './RequisitesForm';
import type { Requisites } from './requisites';

function Form({ side }: { side: 'seller' | 'client' }) {
  const [values, setValues] = useState<Requisites>({ name: 'Черновик' });
  return (
    <>
      <RequisitesForm values={values} onChange={setValues} errors={{}} side={side} />
      <output data-testid="values">{JSON.stringify(values)}</output>
    </>
  );
}

describe('RequisitesForm on the dev stand', () => {
  it('fills the demo requisites of its side', async () => {
    const api = mockApi();
    vi.spyOn(api, 'devRequisites').mockResolvedValue({
      seller: { name: 'ООО «Ромашка»', inn: '7728417603', bic: '044525225' },
      client: { name: 'ООО «Альфа»', inn: '5003102144' },
    });
    renderScreen(<Form side="client" />, { api, path: '/', route: '/' });

    fireEvent.click(screen.getByText('Тестовые реквизиты'));

    await waitFor(() =>
      expect(JSON.parse(screen.getByTestId('values').textContent ?? '{}')).toEqual({
        name: 'ООО «Альфа»',
        inn: '5003102144',
      }),
    );
    expect(
      screen.getByText('Подставлены тестовые реквизиты — они проходят проверку'),
    ).toBeInTheDocument();
  });
});

describe('RequisitesForm registry search', () => {
  it('fills the card from a picked company', async () => {
    const api = mockApi();
    const suggest = vi.spyOn(api, 'suggest').mockResolvedValue([
      {
        title: 'ООО «Ромашка»',
        subtitle: 'ИНН 7707083893 · г Москва',
        values: { name: 'ООО «Ромашка»', inn: '7707083893', kpp: '773601001' },
      },
    ]);
    renderScreen(<Form side="client" />, { api, path: '/', route: '/' });

    const inn = screen.getByRole('combobox', { name: 'ИНН' });
    fireEvent.focus(inn);
    fireEvent.change(inn, { target: { value: '7707' } });
    const option = await screen.findByRole('option', { name: /ООО «Ромашка»/ });
    expect(suggest).toHaveBeenCalledWith('company', '7707');

    fireEvent.click(option);

    expect(JSON.parse(screen.getByTestId('values').textContent ?? '{}')).toEqual({
      name: 'ООО «Ромашка»',
      inn: '7707083893',
      kpp: '773601001',
    });
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    expect(screen.getAllByText('Из реестра')).toHaveLength(3);
  });

  it('does not ask the registry for a short query', async () => {
    const api = mockApi();
    const suggest = vi.spyOn(api, 'suggest').mockResolvedValue([]);
    renderScreen(<Form side="seller" />, { api, path: '/', route: '/' });

    fireEvent.change(screen.getByRole('combobox', { name: 'БИК' }), { target: { value: '04' } });
    await new Promise((resolve) => setTimeout(resolve, 500));

    expect(suggest).not.toHaveBeenCalled();
  });
});
