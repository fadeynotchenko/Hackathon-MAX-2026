// Каталог «Новый документ»: сверху «Свой шаблон», под ним свои шаблоны, затем
// стандартные — каждая сетка под своим заголовком; поиск ищет по обеим.
import { fireEvent, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { Template } from '@/api/client';
import { makeTemplate, mockApi, renderScreen } from '@/test-utils';

import { CreatePage } from './CreatePage';

function template(id: number, title: string, kind: string, isBuiltin = true): Template {
  return makeTemplate({
    id,
    title,
    kind,
    description: '',
    is_builtin: isBuiltin,
    preview: 'Бланк',
  });
}

const invoice = template(1, 'Счёт на оплату', 'invoice');
const offer = template(2, 'Коммерческое предложение', 'offer');
const ownOffer = template(7, 'Фирменный КП', 'offer', false);

function setup(templates: Template[]) {
  const api = mockApi();
  vi.spyOn(api, 'templates').mockResolvedValue(templates);
  renderScreen(<CreatePage />, { api, path: '/create', route: '/create' });
}

function section(title: string): HTMLElement {
  const found = screen.getByText(title).closest('section');
  if (!found) throw new Error(`Нет раздела «${title}»`);
  return found;
}

function follows(first: HTMLElement, second: HTMLElement): boolean {
  return Boolean(first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING);
}

describe('CreatePage', () => {
  it('puts «Свой шаблон» first, then own templates, then the standard ones', async () => {
    setup([invoice, offer, ownOffer]);

    const own = await screen.findByText('Мои шаблоны');
    const standard = screen.getByText('Стандартные');
    expect(follows(screen.getByText('Свой шаблон'), own)).toBe(true);
    expect(follows(own, standard)).toBe(true);
    expect(follows(standard, screen.getByText('Написать боту'))).toBe(true);

    expect(within(section('Мои шаблоны')).getByText('Фирменный КП')).toBeInTheDocument();
    expect(within(section('Мои шаблоны')).queryByText('Счёт на оплату')).toBeNull();
    expect(within(section('Стандартные')).getByText('Счёт на оплату')).toBeInTheDocument();
    expect(screen.queryByText('Ваш шаблон')).toBeNull();
  });

  it('labels the standard templates even without own ones', async () => {
    setup([invoice, offer]);

    expect(await screen.findByText('Стандартные')).toBeInTheDocument();
    expect(screen.queryByText('Мои шаблоны')).toBeNull();
    expect(follows(screen.getByText('Свой шаблон'), screen.getByText('Стандартные'))).toBe(true);
  });

  it('searches both grids and hides a section without matches', async () => {
    setup([
      invoice,
      offer,
      template(3, 'Договор оказания услуг', 'contract'),
      template(4, 'Акт выполненных работ', 'other'),
      template(5, 'Счёт-оферта', 'invoice'),
      ownOffer,
      template(8, 'Счёт для своих', 'invoice', false),
    ]);
    const search = await screen.findByRole('searchbox');
    expect(follows(screen.getByText('Свой шаблон'), search)).toBe(true);
    expect(follows(search, screen.getByText('Мои шаблоны'))).toBe(true);

    fireEvent.change(search, { target: { value: 'счёт' } });
    expect(within(section('Мои шаблоны')).getByText('Счёт для своих')).toBeInTheDocument();
    expect(within(section('Стандартные')).getByText('Счёт-оферта')).toBeInTheDocument();
    expect(screen.queryByText('Фирменный КП')).toBeNull();

    fireEvent.change(search, { target: { value: 'фирменный' } });
    expect(screen.queryByText('Стандартные')).toBeNull();
    expect(screen.getByText('Фирменный КП')).toBeInTheDocument();

    fireEvent.change(search, { target: { value: 'накладная' } });
    expect(screen.getByText('Ничего не нашлось')).toBeInTheDocument();
    expect(screen.getByText('Свой шаблон')).toBeInTheDocument();
  });
});
