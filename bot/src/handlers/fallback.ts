// Последний обработчик: любое текстовое сообщение, не распознанное выше.
import type { Bot } from '@maxhub/max-bot-api';

import type { BotContext } from '../context.js';
import { mainKeyboard, type MainKeyboardOptions } from '../keyboards/main.js';

export const FALLBACK_TEXT =
  'Я понимаю только команды. Откройте мини-приложение или наберите /help.';

export function registerFallback(bot: Bot<BotContext>, keyboard: MainKeyboardOptions): void {
  bot.on('message_created', async (ctx) => {
    // В группах, куда бота добавили, на каждое сообщение отвечать нельзя.
    if (ctx.message.recipient.chat_type !== 'dialog') return;
    await ctx.reply(FALLBACK_TEXT, { attachments: [mainKeyboard(keyboard)] });
  });
}
