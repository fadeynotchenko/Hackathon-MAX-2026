import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it } from 'vitest';

import { FieldInput } from './FieldInput';

function Inn({ error }: { error?: string }) {
  const [value, setValue] = useState('');
  return <FieldInput label="ИНН" type="inn" value={value} onChange={setValue} error={error} />;
}

describe('FieldInput requisites check', () => {
  it('shows a wrong INN once the person leaves the field, not while typing', () => {
    render(<Inn />);
    const input = screen.getByLabelText('ИНН');
    fireEvent.change(input, { target: { value: '1234567890' } });
    expect(screen.queryByText('ИНН не проходит проверку')).toBeNull();

    fireEvent.blur(input);
    expect(screen.getByText('ИНН не проходит проверку')).toBeInTheDocument();
    expect(input).toHaveAttribute('aria-invalid', 'true');

    fireEvent.change(input, { target: { value: '7728417603' } });
    expect(screen.queryByText('ИНН не проходит проверку')).toBeNull();
  });

  it('prefers the server error', () => {
    render(<Inn error="«ИНН»: такой организации нет" />);
    const input = screen.getByLabelText('ИНН');
    fireEvent.change(input, { target: { value: '1' } });
    fireEvent.blur(input);
    expect(screen.getByText('«ИНН»: такой организации нет')).toBeInTheDocument();
    expect(screen.queryByText('ИНН не проходит проверку')).toBeNull();
  });
});
