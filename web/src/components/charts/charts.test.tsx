import { MaxUI } from '@maxhub/max-ui';
import { fireEvent, render, screen, within } from '@testing-library/react';
import type { ReactElement } from 'react';
import { describe, expect, it } from 'vitest';

import { BarList } from './BarList';
import { ColumnChart } from './ColumnChart';
import { LineChart } from './LineChart';
import { ChartCard, ChartTable } from './parts';
import { niceScale } from './scale';

function renderUi(element: ReactElement) {
  return render(
    <MaxUI colorScheme="light" platform="ios">
      {element}
    </MaxUI>,
  );
}

const live = (chart: HTMLElement) => chart.querySelector('[aria-live]')?.textContent;

describe('niceScale', () => {
  it('rounds the axis to readable integer steps', () => {
    expect(niceScale(0)).toEqual({ max: 1, ticks: [0, 1] });
    expect(niceScale(2)).toEqual({ max: 2, ticks: [0, 1, 2] });
    expect(niceScale(7)).toEqual({ max: 10, ticks: [0, 5, 10] });
    expect(niceScale(42)).toEqual({ max: 60, ticks: [0, 20, 40, 60] });
  });
});

describe('LineChart', () => {
  const series = [
    { key: 'week', name: 'За 7 дней', tone: 'context' as const, values: [4, 6, 9] },
    { key: 'day', name: 'За день', tone: 'accent' as const, values: [1, 3, 2] },
  ];

  it('reads every series of the chosen day from the keyboard', () => {
    renderUi(
      <LineChart label="Активные" labels={['1 сент.', '2 сент.', '3 сент.']} series={series} />,
    );
    const chart = screen.getByRole('group', { name: 'Активные' });

    fireEvent.focus(chart);
    expect(live(chart)).toBe('3 сент., За 7 дней: 9, За день: 2');
    fireEvent.keyDown(chart, { key: 'ArrowLeft' });
    expect(live(chart)).toBe('2 сент., За 7 дней: 6, За день: 3');
    fireEvent.keyDown(chart, { key: 'Home' });
    expect(live(chart)).toContain('1 сент.');
    fireEvent.keyDown(chart, { key: 'Escape' });
    expect(live(chart)).toBe('');
  });

  it('labels line ends only while nothing is selected', () => {
    const { container } = renderUi(
      <LineChart label="Активные" labels={['1 сент.', '2 сент.', '3 сент.']} series={series} />,
    );
    const endLabels = () =>
      [...container.querySelectorAll('.chart__label')].map((node) => node.textContent);
    expect(endLabels()).toEqual(['9', '2']);
    fireEvent.focus(screen.getByRole('group'));
    expect(endLabels()).toEqual([]);
  });
});

describe('ColumnChart', () => {
  const columns = [
    { key: 'a', label: '1 сент.', value: 2 },
    {
      key: 'b',
      label: '2 сент.',
      value: 5,
      details: [{ key: 'invoice', name: 'Счета', value: '4' }],
    },
    { key: 'c', label: '3 сент.', value: 0 },
  ];

  it('labels the peak and skips empty days instead of drawing a stub', () => {
    const { container } = renderUi(
      <ColumnChart columns={columns} name="Создано" label="Документы" />,
    );
    expect(container.querySelectorAll('.chart__bar')).toHaveLength(2);
    expect(container.querySelector('.chart__label')?.textContent).toBe('5');
  });

  it('shows the value and its breakdown for the chosen column', () => {
    renderUi(<ColumnChart columns={columns} name="Создано" label="Документы" />);
    const chart = screen.getByRole('group', { name: 'Документы' });

    fireEvent.focus(chart);
    fireEvent.keyDown(chart, { key: 'ArrowLeft' });

    expect(live(chart)).toBe('2 сент., Создано: 5, Счета: 4');
    expect(chart.querySelector('.chart-tooltip')?.textContent).toContain('Счета');
  });
});

describe('BarList', () => {
  it('scales bars to the largest value and labels every row', () => {
    renderUi(
      <BarList
        label="Виды"
        rows={[
          { key: 'invoice', label: 'Счета', value: 4, note: '80 %' },
          { key: 'offer', label: 'КП', value: 2 },
          { key: 'contract', label: 'Договоры', value: 0 },
        ]}
      />,
    );
    const rows = within(screen.getByRole('list', { name: 'Виды' })).getAllByRole('listitem');
    const width = (row: HTMLElement) =>
      (row.querySelector('.bar-row__bar') as HTMLElement).style.width;

    expect(rows[0]).toHaveTextContent('Счета4 · 80 %');
    expect(width(rows[0] as HTMLElement)).toBe('max(2px, 100%)');
    expect(width(rows[1] as HTMLElement)).toBe('max(2px, 50%)');
    expect(width(rows[2] as HTMLElement)).toBe('0px');
  });

  it('colours ordered stages as steps and context rows in gray', () => {
    const { container } = renderUi(
      <>
        <BarList
          label="Воронка"
          ordinal
          rows={[
            { key: 'a', label: 'Создан', value: 3 },
            { key: 'b', label: 'Готов', value: 2 },
          ]}
        />
        <BarList label="Источники" rows={[{ key: 'm', label: 'Вручную', value: 1, muted: true }]} />
      </>,
    );
    const classes = [...container.querySelectorAll('.bar-row__bar')].map((bar) => bar.className);
    expect(classes).toEqual([
      'bar-row__bar bar-row__bar--step-0',
      'bar-row__bar bar-row__bar--step-1',
      'bar-row__bar bar-row__bar--context',
    ]);
  });
});

describe('ChartCard', () => {
  it('switches between the chart and its table', () => {
    renderUi(
      <ChartCard
        title="Новые пользователи"
        table={<ChartTable columns={['День', 'Новых']} rows={[['1 сент.', '3']]} />}
      >
        <div>график</div>
      </ChartCard>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Таблица' }));

    expect(screen.queryByText('график')).toBeNull();
    expect(screen.getByRole('rowheader', { name: '1 сент.' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'График' }));
    expect(screen.getByText('график')).toBeInTheDocument();
  });
});
