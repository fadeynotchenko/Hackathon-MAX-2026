// Стенд вне MAX: кнопка «Тестовые реквизиты» подставляет сходящийся набор своей
// стороны — ИНН, БИК и счета проходят проверку, руками их не подобрать.
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
