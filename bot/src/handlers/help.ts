import type { Bot } from '@maxhub/max-bot-api';

import type { BotContext } from '../context.js';
import { CALLBACKS, mainKeyboard, type MainKeyboardOptions } from '../keyboards/main.js';

export const HELP_TEXT = [
  'Команды:',
  '/start — открыть главное меню',
  '/help — эта подсказка',
  '',
  'Основная работа идёт в мини-приложении: кнопка «Открыть приложение».',
].join('\n');

export function registerHelp(bot: Bot<BotContext>, keyboard: MainKeyboardOptions): void {
  bot.command('help', async (ctx) => {
    await ctx.reply(HELP_TEXT, { attachments: [mainKeyboard(keyboard)] });
  });
  bot.action(CALLBACKS.help, async (ctx) => {
    await ctx.answerOnCallback({ message: { text: HELP_TEXT } });
  });
}
