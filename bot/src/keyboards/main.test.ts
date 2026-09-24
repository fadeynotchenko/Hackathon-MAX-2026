import { describe, expect, it } from 'vitest';

import { mainKeyboard } from './main.js';

function buttons(keyboard: ReturnType<typeof mainKeyboard>) {
  return keyboard.payload.buttons;
}

describe('main keyboard', () => {
  it('opens the mini app on the right screen when its name is configured', () => {
    const rows = buttons(mainKeyboard({ miniAppName: 't409_hakaton_max_bot' }));
    expect(rows[0]?.[0]).toMatchObject({
      type: 'open_app',
      text: 'Создать документ',
      web_app: 't409_hakaton_max_bot',
      payload: 'create',
    });
    expect(rows[1]?.[0]).toMatchObject({ type: 'open_app', text: 'Архив', payload: 'archive' });
    expect(rows[1]?.[1]).toMatchObject({ type: 'callback', payload: 'help' });
  });

  it('drops app buttons without a name instead of sending web_app: null', () => {
    // MAX отвечает 400 на пустой web_app и роняет всё сообщение, а не одну кнопку.
    const rows = buttons(mainKeyboard());
    expect(rows.flat().some((button) => button.type === 'open_app')).toBe(false);
    expect(rows).toEqual([[expect.objectContaining({ type: 'callback', payload: 'help' })]]);
  });
});
