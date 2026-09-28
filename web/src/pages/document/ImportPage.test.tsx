// Документ по своему файлу: файл уходит на сервер, человек попадает в форму
// документа, где значения — как в файле, а над формой сказано, что нашлось.
import { fireEvent, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { DocumentImport } from '@/api/client';
import { makeDocument, makeTemplate, mockApi, renderScreen } from '@/test-utils';

import { importNotice } from './imported';
import { ImportPage } from './ImportPage';

function imported(overrides: Partial<DocumentImport> = {}): DocumentImport {
  return {
    document: makeDocument({
      id: 12,
      template: makeTemplate({ id: 30, is_builtin: false, in_library: false, can_keep: true }),
    }),
    format: 'docx',
    found_by: 'assistant',
    notice: null,
    ...overrides,
  };
}

describe('ImportPage', () => {
  it('sends the file and opens the form of the new document', async () => {
    const api = mockApi();
    const importDocument = vi.spyOn(api, 'importDocument').mockResolvedValue(imported());
    const { container } = renderScreen(<ImportPage />, {
      api,
      path: '/documents/import',
      route: '/documents/import',
    });

    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(['docx'], 'Договор с Альфой.docx');
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() =>
      expect(screen.getByTestId('location')).toHaveTextContent('/documents/12/fill'),
    );
    expect(importDocument).toHaveBeenCalledWith(file);
  });

  it('explains a file without places', async () => {
    const api = mockApi();
    vi.spyOn(api, 'importDocument').mockRejectedValue(new Error('В файле не нашлось мест'));
    const { container } = renderScreen(<ImportPage />, {
      api,
      path: '/documents/import',
      route: '/documents/import',
    });
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(['x'], 'a.pdf')] } });
    expect(await screen.findByText('Не удалось прочитать файл')).toBeInTheDocument();
  });
});

describe('importNotice', () => {
  it('says how many places were found and by whom', () => {
    const notice = importNotice(imported({ found_by: 'rules' }));
    expect(notice.title).toBe('Нашли 4 места для данных по линейкам и реквизитам');
    expect(notice.tone).toBe('success');
  });

  it('passes the PDF warning through', () => {
    const notice = importNotice(
      imported({ format: 'pdf', notice: 'Помощник выключен — отметьте места для данных сами' }),
    );
    expect(notice).toMatchObject({
      tone: 'info',
      text: 'Помощник выключен — отметьте места для данных сами',
    });
  });
});
