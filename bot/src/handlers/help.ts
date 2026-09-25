import type { Bot } from '@maxhub/max-bot-api';

import type { BotContext } from '../context.js';
import { CALLBACKS, mainKeyboard, type MainKeyboardOptions } from '../keyboards/main.js';

// Разметка — HTML MAX, как у приветствия.
export const HELP_TEXT = [
  '❓ <b>Как со мной работать</b>',
  '',
  '<b>1. Опишите документ</b>',
  'Обычным сообщением: какой документ нужен и с какими данными.',
  '<i>«Счёт на 50 000 для ООО Ромашка за консультацию, оплата до 10 октября»</i>',
  '',
  '<b>2. Поправьте или спросите</b>',
  '✏️ <i>«Поменяй сумму на 60 000»</i>',
  '🔍 <i>«Чего не хватает?»</i>',
  '',
  '<b>3. Пришлите вместо текста</b>',
  '🎙 Голосовое сообщение',
  '📷 Фото карточки предприятия, счёта или договора',
  '📎 Скан в PDF или DOCX',
  'Реквизиты распознаю и покажу на проверку.',
  '',
  '<b>Команды</b>',
  '/start — главное меню',
  '/help — эта подсказка',
].join('\n');

export function registerHelp(bot: Bot<BotContext>, keyboard: MainKeyboardOptions): void {
  bot.command('help', async (ctx) => {
    await ctx.reply(HELP_TEXT, { format: 'html', attachments: [mainKeyboard(keyboard)] });
  });
  bot.action(CALLBACKS.help, async (ctx) => {
    await ctx.answerOnCallback({ message: { text: HELP_TEXT, format: 'html' } });
  });
}
