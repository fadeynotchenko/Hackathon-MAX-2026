// Клавиатуры бота. Тексты кнопок живут здесь же: у бота нет второго языка,
// а вынос в i18n без второго языка — каталог «на будущее».
import { Keyboard } from '@maxhub/max-bot-api';
import type { OpenAppButton } from '@maxhub/max-bot-api/types';

export const CALLBACKS = {
  help: 'help',
  profile: 'profile',
} as const;

export interface MainKeyboardOptions {
  // Имя мини-приложения для кнопки open_app. Пусто — откроется мини-апп бота по умолчанию.
  miniAppName?: string;
}

// Кнопка open_app: web_app указывается только когда задано имя мини-аппа.
// Пустая строка от Keyboard.button.openApp ушла бы в API как web_app="" и
// не открыла бы мини-апп бота по умолчанию.
export function openAppButton(text: string, miniAppName?: string): OpenAppButton {
  return miniAppName
    ? { type: 'open_app', text, web_app: miniAppName }
    : { type: 'open_app', text };
}

export function mainKeyboard(options: MainKeyboardOptions = {}) {
  return Keyboard.inlineKeyboard([
    [openAppButton('Открыть приложение', options.miniAppName)],
    [
      Keyboard.button.callback('Помощь', CALLBACKS.help),
      Keyboard.button.callback('Профиль', CALLBACKS.profile),
    ],
  ]);
}
