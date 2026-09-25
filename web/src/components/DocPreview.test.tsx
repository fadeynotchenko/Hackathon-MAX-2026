import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { DocPreview } from './DocPreview';

describe('DocPreview', () => {
  it('marks only the server blank, not signature lines of the form', () => {
    const text = 'в лице __________, заключили\nИсполнитель ______________________ / Иванов /';
    const { container } = render(<DocPreview text={text} />);
    const marks = container.querySelectorAll('mark');
    expect(marks).toHaveLength(1);
    expect(marks[0]?.textContent).toBe('__________');
    const lines = [...container.querySelectorAll('.sheet__line')].map((p) => p.textContent);
    expect(lines).toEqual(text.split('\n'));
  });

  it('lays out lines as paragraphs with the first one as heading, like the DOCX builder', () => {
    const text = '\nСчёт на оплату № 17\n\nПоставщик: ООО «Лютик»';
    const { container } = render(<DocPreview text={text} />);
    const heading = container.querySelector('.sheet__line--heading');
    expect(heading?.textContent).toBe('Счёт на оплату № 17');
    expect(container.querySelectorAll('.sheet__line')).toHaveLength(4);
  });

  it('shows an empty template without marks and hides the mini sheet from screen readers', () => {
    const { container } = render(<DocPreview text="Договор № __________" marks={false} mini />);
    expect(container.querySelector('mark')).toBeNull();
    expect(container.querySelector('.sheet__page')?.getAttribute('aria-hidden')).toBe('true');
  });
});
