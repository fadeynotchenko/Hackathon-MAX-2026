import { describe, expect, it } from 'vitest';

import { ApiError } from '@/api/client';

import { OFFLINE_TEXT, errorText } from './useAsync';

describe('errorText', () => {
  it('shows the server message, the network hint or the fallback', () => {
    expect(errorText(new ApiError(404, 'document.not_found', 'Документ не найден', null))).toBe(
      'Документ не найден',
    );
    expect(errorText(new TypeError('Failed to fetch'))).toBe(OFFLINE_TEXT);
    expect(errorText(new Error('boom'), 'Не удалось сохранить')).toBe('Не удалось сохранить');
  });
});
