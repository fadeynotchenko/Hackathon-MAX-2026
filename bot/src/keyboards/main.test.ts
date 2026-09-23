import { describe, expect, it } from 'vitest';

import { mainKeyboard } from './main.js';

function buttons(keyboard: ReturnType<typeof mainKeyboard>) {
  return keyboard.payload.buttons;
}

describe('main keyboard', () => {
  it('opens the mini app when its name is configured', () => {
    const rows = buttons(mainKeyboard({ miniAppName: 't409_hakaton_max_bot' }));
    expect(rows[0]?.[0]).toMatchObject({ type: 'open_app', web_app: 't409_hakaton_max_bot' });
  });

  it('drops the button without a name instead of sending web_app: null', () => {
    // MAX отвечает 400 на пустой web_app и роняет всё сообщение, а не одну кнопку.
    const rows = buttons(mainKeyboard());
    expect(rows.flat().some((button) => button.type === 'open_app')).toBe(false);
    expect(rows[0]).toHaveLength(2);
  });
});
