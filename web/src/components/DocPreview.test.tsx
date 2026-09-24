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
    expect(container.textContent).toBe(text);
  });
});
