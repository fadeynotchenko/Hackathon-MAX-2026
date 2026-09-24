// Клавиатуры бота. Тексты кнопок живут здесь же: у бота нет второго языка,
// а вынос в i18n без второго языка — каталог «на будущее».
import { Keyboard } from '@maxhub/max-bot-api';

export const CALLBACKS = {
  help: 'help',
  // Кнопки «Профиль» в клавиатуре больше нет (профиль — вкладка мини-аппа),
  // но в уже отправленных сообщениях она осталась и должна отвечать.
  profile: 'profile',
} as const;

// Экраны мини-аппа для кнопок open_app: payload приходит в initData как
// start_param, и мини-апп открывается сразу на нужной вкладке (web/src/lib/startRoute.ts).
export const APP_SCREENS = {
  create: 'create',
  archive: 'archive',
} as const;

export interface MainKeyboardOptions {
  // Имя мини-приложения для кнопки open_app; у нашего бота совпадает с его username.
  miniAppName?: string;
}

// Кнопки open_app появляются только с именем мини-аппа: MAX отвечает
// «400 Field 'webApp' cannot be null» и не доставляет сообщение целиком,
// если web_app пуст (проверено на боте t409_hakaton_max_bot 2026-09-24).
// Без имени приветствие уходит только с «Помощью», а не теряется.
export function mainKeyboard(options: MainKeyboardOptions = {}) {
  const rows: Parameters<typeof Keyboard.inlineKeyboard>[0] = [];
  const help = Keyboard.button.callback('Помощь', CALLBACKS.help);
  const app = options.miniAppName;
  if (app) {
    rows.push([
      { type: 'open_app', text: 'Создать документ', web_app: app, payload: APP_SCREENS.create },
    ]);
    rows.push([
      { type: 'open_app', text: 'Архив', web_app: app, payload: APP_SCREENS.archive },
      help,
    ]);
  } else {
    rows.push([help]);
  }
  return Keyboard.inlineKeyboard(rows);
}
