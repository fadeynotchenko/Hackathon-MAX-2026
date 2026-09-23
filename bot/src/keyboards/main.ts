// Клавиатуры бота. Тексты кнопок живут здесь же: у бота нет второго языка,
// а вынос в i18n без второго языка — каталог «на будущее».
import { Keyboard } from '@maxhub/max-bot-api';

export const CALLBACKS = {
  help: 'help',
  profile: 'profile',
} as const;

export interface MainKeyboardOptions {
  // Имя мини-приложения для кнопки open_app; у нашего бота совпадает с его username.
  miniAppName?: string;
}

// Кнопка open_app появляется только с именем мини-аппа: MAX отвечает
// «400 Field 'webApp' cannot be null» и не доставляет сообщение целиком,
// если web_app пуст (проверено на боте t409_hakaton_max_bot 2026-09-24).
// Без имени приветствие уходит без кнопки, а не теряется.
export function mainKeyboard(options: MainKeyboardOptions = {}) {
  const rows: Parameters<typeof Keyboard.inlineKeyboard>[0] = [];
  if (options.miniAppName) {
    rows.push([
      { type: 'open_app', text: 'Открыть приложение', web_app: options.miniAppName },
    ]);
  }
  rows.push([
    Keyboard.button.callback('Помощь', CALLBACKS.help),
    Keyboard.button.callback('Профиль', CALLBACKS.profile),
  ]);
  return Keyboard.inlineKeyboard(rows);
}
