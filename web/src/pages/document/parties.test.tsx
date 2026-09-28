// Стороны документа из формы: ячейки «Клиент» и «От кого» сохраняют правки и
// ведут к выбору; выбор уходит на сервер только при смене стороны и возвращает
// в форму с плашкой. Новая карточка или организация из формы профиля
// подставляется сразу и один раз (в том числе под StrictMode), а «назад» после
// неё ведёт в форму документа, а не в форму профиля.
import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';
import { StrictMode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { ApiClient, Counterparty, DocumentView, Organization } from '@/api/client';
import { CounterpartyPage } from '@/pages/profile/CounterpartyPage';
import { OrganizationPage } from '@/pages/profile/OrganizationPage';
import { activeScreen, makeDocument, makeTemplate, mockApi, renderScreen } from '@/test-utils';

import { ClientPickPage } from './ClientPickPage';
import { dropNotice, peekNotice } from './fillMethods';
import { FillPage } from './FillPage';
import { SellerPickPage } from './SellerPickPage';

function card(id: number, name: string, inn: string): Counterparty {
  return {
    id,
    name,
    inn,
    values: { name, inn },
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-01T00:00:00Z',
  };
}

function organization(id: number, name: string, isDefault = false): Organization {
  return {
    id,
    name,
    inn: '7707083893',
    is_default: isDefault,
    values: { name },
    created_at: '2026-09-01T00:00:00Z',
    updated_at: '2026-09-01T00:00:00Z',
  };
}

const alpha = card(1, 'ООО «Альфа»', '7736207543');
const beta = card(2, 'ООО «Бета»', '7707083893');
const master = organization(1, 'ООО «Мастер»', true);
const second = organization(2, 'ИП Петров');

const withAlpha = makeDocument({
  counterparty_id: 1,
  organization_id: 1,
  values: {
    ...makeDocument().values,
    client_name: {
      value: 'ООО «Альфа»',
      source: 'counterparty',
      confirmed: true,
      fragment: null,
      confidence: null,
    },
  },
});

// Форма, оба выбора и формы профиля в одном роутере — чтобы пройти туда и
// обратно по истории. StrictMode — проверить, что двойной эффект не шлёт выбор дважды.
function renderForm(api: ApiClient) {
  return renderScreen(
    <StrictMode>
      <FillPage />
    </StrictMode>,
    {
      api,
      path: '/documents/:documentId/fill',
      route: '/documents/7/fill',
      routes: [
        {
          path: '/documents/:documentId/fill/client',
          element: (
            <StrictMode>
              <ClientPickPage />
            </StrictMode>
          ),
        },
        {
          path: '/documents/:documentId/fill/seller',
          element: (
            <StrictMode>
              <SellerPickPage />
            </StrictMode>
          ),
        },
        { path: '/profile/counterparties/new', element: <CounterpartyPage /> },
        { path: '/profile/organizations/new', element: <OrganizationPage /> },
      ],
    },
  );
}

function setup(doc: DocumentView = makeDocument(), organizations = [master, second]) {
  const api = mockApi();
  const load = vi.spyOn(api, 'document').mockResolvedValue(doc);
  vi.spyOn(api, 'organizations').mockResolvedValue(organizations);
  vi.spyOn(api, 'counterparties').mockResolvedValue([alpha, beta]);
  const setParties = vi.spyOn(api, 'setParties').mockResolvedValue(doc);
  return { api, load, setParties };
}

function location() {
  return screen.getByTestId('location');
}

afterEach(() => {
  dropNotice(7);
});

describe('parties in the form', () => {
  it('shows the attached card and the organization', async () => {
    const { api } = setup(withAlpha);
    renderForm(api);

    expect(await screen.findByText('Из карточки клиентов')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /ООО «Альфа».*Из карточки клиентов/ })).toBeVisible();
    expect(screen.getByRole('button', { name: /От кого.*ООО «Мастер»/ })).toBeVisible();
  });

  it('has no party cells in a template without party fields', async () => {
    const template = makeTemplate();
    const { api } = setup(
      makeDocument({
        template: { ...template, fields: template.fields.filter((f) => f.group === 'Предмет') },
        values: {},
      }),
    );
    renderForm(api);

    expect(await screen.findByLabelText(/Сумма к оплате/)).toBeInTheDocument();
    expect(screen.queryByText('Выбрать из клиентов')).toBeNull();
    expect(screen.queryByText('От кого')).toBeNull();
  });

  it('saves edits, picks a card and comes back with a notice', async () => {
    const { api, load, setParties } = setup();
    const setFields = vi.spyOn(api, 'setFields').mockResolvedValue(makeDocument());
    load.mockResolvedValueOnce(makeDocument()).mockResolvedValueOnce(makeDocument());
    renderForm(api);

    fireEvent.change(await screen.findByLabelText(/Сумма к оплате/), {
      target: { value: '1 000' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Выбрать из клиентов' }));
    await waitFor(() => expect(location()).toHaveTextContent('/documents/7/fill/client'));
    expect(setFields).toHaveBeenCalledWith(7, { total: '1 000' });

    fireEvent.click(await screen.findByRole('button', { name: /ООО «Бета»/ }));

    expect(await screen.findByText('Реквизиты клиента подставлены')).toBeInTheDocument();
    expect(location()).toHaveTextContent(/^\/documents\/7\/fill$/);
    expect(setParties).toHaveBeenCalledTimes(1);
    expect(setParties).toHaveBeenCalledWith(7, { counterparty_id: 2 });
  });

  it('just goes back when the attached card is tapped', async () => {
    const { api, setParties } = setup(withAlpha);
    renderForm(api);

    fireEvent.click(await screen.findByRole('button', { name: /ООО «Альфа».*Из карточки/ }));
    const current = await screen.findByRole('button', { name: /ООО «Альфа».*Выбран/ });
    fireEvent.click(current);

    await waitFor(() => expect(location()).toHaveTextContent(/^\/documents\/7\/fill$/));
    expect(setParties).not.toHaveBeenCalled();
  });

  it('detaches the card', async () => {
    const { api, setParties } = setup(withAlpha);
    renderForm(api);

    fireEvent.click(await screen.findByRole('button', { name: /ООО «Альфа».*Из карточки/ }));
    fireEvent.click(await screen.findByRole('button', { name: 'Без карточки' }));

    expect(await screen.findByText('Реквизиты из карточки убраны')).toBeInTheDocument();
    expect(setParties).toHaveBeenCalledWith(7, { counterparty_id: null });
  });

  it('applies a new card once and comes back to the form', async () => {
    const { api, setParties } = setup();
    const create = vi
      .spyOn(api, 'createCounterparty')
      .mockResolvedValue(card(5, 'ООО «Гамма»', ''));
    renderForm(api);

    fireEvent.click(await screen.findByRole('button', { name: 'Выбрать из клиентов' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Новый клиент' }));
    fireEvent.change(await within(activeScreen()).findByLabelText(/Название/), {
      target: { value: 'ООО «Гамма»' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить и продолжить' }));

    expect(await screen.findByText('Реквизиты клиента подставлены')).toBeInTheDocument();
    // Форма профиля заменила себя выбором: один шаг назад — и мы в форме документа.
    expect(location()).toHaveTextContent(/^\/documents\/7\/fill$/);
    expect(create).toHaveBeenCalledTimes(1);
    expect(setParties).toHaveBeenCalledTimes(1);
    expect(setParties).toHaveBeenCalledWith(7, { counterparty_id: 5 });
  });

  it('comes back to the form when a new card is not saved', async () => {
    const { api, setParties } = setup();
    renderForm(api);

    fireEvent.click(await screen.findByRole('button', { name: 'Выбрать из клиентов' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Новый клиент' }));
    await waitFor(() => expect(location()).toHaveTextContent('/profile/counterparties/new'));
    fireEvent.click(screen.getByRole('button', { name: 'Назад' }));

    await waitFor(() => expect(location()).toHaveTextContent(/^\/documents\/7\/fill$/));
    expect(setParties).not.toHaveBeenCalled();
  });

  it('says why the card was not applied and stays', async () => {
    const { api, setParties } = setup();
    setParties.mockRejectedValue(new Error('boom'));
    renderForm(api);

    fireEvent.click(await screen.findByRole('button', { name: 'Выбрать из клиентов' }));
    fireEvent.click(await screen.findByRole('button', { name: /ООО «Бета»/ }));

    expect(await screen.findByText('Не удалось подставить реквизиты')).toBeInTheDocument();
    expect(location()).toHaveTextContent('/documents/7/fill/client');
    expect(screen.getByRole('button', { name: /ООО «Бета»/ })).not.toHaveAttribute(
      'aria-disabled',
      'true',
    );
  });

  it('does not step back again when the person left during the request', async () => {
    const { api, setParties } = setup();
    let applied!: (document: DocumentView) => void;
    setParties.mockReturnValue(
      new Promise((resolve) => {
        applied = resolve;
      }),
    );
    renderForm(api);

    fireEvent.click(await screen.findByRole('button', { name: 'Выбрать из клиентов' }));
    fireEvent.click(await screen.findByRole('button', { name: /ООО «Бета»/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Назад' }));
    expect(await screen.findByText('Выбрать из клиентов')).toBeInTheDocument();

    await act(async () => applied(makeDocument()));

    expect(location()).toHaveTextContent(/^\/documents\/7\/fill$/);
    expect(peekNotice(7)).toBeNull();
  });

  it('picks another own organization', async () => {
    const { api, setParties } = setup(withAlpha);
    renderForm(api);

    fireEvent.click(await screen.findByRole('button', { name: /От кого.*ООО «Мастер»/ }));
    expect(await screen.findByRole('radio', { name: 'ООО «Мастер»' })).toBeChecked();
    fireEvent.click(screen.getByRole('radio', { name: 'ИП Петров' }));

    expect(await screen.findByText('Реквизиты организации подставлены')).toBeInTheDocument();
    expect(location()).toHaveTextContent(/^\/documents\/7\/fill$/);
    // Radio и сама строка ловят один тап — запрос один.
    expect(setParties).toHaveBeenCalledTimes(1);
    expect(setParties).toHaveBeenCalledWith(7, { organization_id: 2 });
  });

  it('adds the first own organization straight from the form', async () => {
    const { api, setParties } = setup(makeDocument(), []);
    vi.spyOn(api, 'createOrganization').mockResolvedValue(organization(3, 'ООО «Новая»', true));
    renderForm(api);

    fireEvent.click(await screen.findByRole('button', { name: /Добавить свою организацию/ }));
    await waitFor(() => expect(location()).toHaveTextContent('/profile/organizations/new'));
    fireEvent.change(within(activeScreen()).getByLabelText(/Название/), {
      target: { value: 'ООО «Новая»' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить и продолжить' }));

    expect(await screen.findByText('Реквизиты организации подставлены')).toBeInTheDocument();
    expect(location()).toHaveTextContent(/^\/documents\/7\/fill$/);
    expect(setParties).toHaveBeenCalledTimes(1);
    expect(setParties).toHaveBeenCalledWith(7, { organization_id: 3 });
  });
});
