import type { Bot } from '@maxhub/max-bot-api';

import type { BotContext } from '../context.js';
import { CALLBACKS, mainKeyboard, type MainKeyboardOptions } from '../keyboards/main.js';

export const HELP_TEXT = [
  'Напишите обычным сообщением, какой документ нужен и с какими данными:',
  '«Счёт на 50 000 для ООО Ромашка за консультацию, оплата до 10 октября».',
  'Можно поправлять («поменяй сумму на 60 000») и спрашивать («чего не хватает?»).',
  'Вместо текста подойдёт голосовое или фото карточки предприятия, счёта, договора:',
  'реквизиты распознаю и подставлю после вашего «Всё верно».',
  '',
  'Команды:',
  '/start — главное меню',
  '/help — эта подсказка',
].join('\n');

export function registerHelp(bot: Bot<BotContext>, keyboard: MainKeyboardOptions): void {
  bot.command('help', async (ctx) => {
    await ctx.reply(HELP_TEXT, { attachments: [mainKeyboard(keyboard)] });
  });
  bot.action(CALLBACKS.help, async (ctx) => {
    await ctx.answerOnCallback({ message: { text: HELP_TEXT } });
  });
}
