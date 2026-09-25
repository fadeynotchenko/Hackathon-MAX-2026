import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { TemplateThumb } from './TemplateThumb';

describe('TemplateThumb', () => {
  it('draws a readable blank form, not loading bars', () => {
    const { container } = render(<TemplateThumb kind="invoice" />);
    expect(container.textContent).toContain('Счёт на оплату');
    expect(container.textContent).toContain('Итого');
    expect(container.querySelectorAll('.thumb__blank').length).toBeGreaterThan(0);
  });

  it('tells kinds apart: a contract has signatures, an invoice does not', () => {
    const contract = render(<TemplateThumb kind="contract" />).container;
    const invoice = render(<TemplateThumb kind="invoice" />).container;
    expect(contract.querySelector('.thumb__sign')?.textContent).toBe('ИсполнительЗаказчик');
    expect(invoice.querySelector('.thumb__sign')).toBeNull();
  });

  it('falls back to a generic form for a custom template kind', () => {
    const { container } = render(<TemplateThumb kind="act" large />);
    expect(container.textContent).toContain('Документ');
    expect(container.firstElementChild?.className).toBe('thumb thumb--large');
  });
});
