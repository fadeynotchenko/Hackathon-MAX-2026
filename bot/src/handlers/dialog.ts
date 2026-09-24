// Диалог с помощником: текст и нажатия кнопок документов уходят в ядро, ответ
// приходит событием notify.user. Бот здесь только канал: модель, документы и
// права живут в ядре, поэтому тот же диалог работает и из мини-аппа.
import type { Bot } from '@maxhub/max-bot-api';

import type { BotContext } from '../context.js';
import type { EventPublisher } from '../events/publisher.js';
import type { Logger } from '../logger.js';

export const DOC_ACTION = /^doc:/;
export const NON_TEXT_HINT =
  'Пока я понимаю только текст. Напишите, какой документ нужен, например: «Счёт на 50 000 для ООО Ромашка за консультацию».';
export const UNKNOWN_COMMAND_TEXT =
  'Такой команды нет. Наберите /help или просто напишите, что нужно.';

export interface DialogDeps {
  publisher: EventPublisher;
  log: Logger;
}

export function registerDialog(bot: Bot<BotContext>, deps: DialogDeps): void {
  bot.action(DOC_ACTION, async (ctx) => {
    const payload = ctx.callback?.payload;
    const user = ctx.user;
    if (!payload || !user || ctx.chatId === undefined || ctx.chatId === null) return;
    await deps.publisher.callback({
      max_user_id: user.user_id,
      chat_id: ctx.chatId,
      payload,
    });
    // Снимаем кнопки с нажатого сообщения: второе нажатие на «прислать файл»
    // собрало бы и отправило документ ещё раз.
    const original = ctx.message?.body.text;
    if (!original) return;
    try {
      await ctx.answerOnCallback({ message: { text: original, attachments: [] } });
    } catch (err) {
      deps.log.warn({ event: 'dialog.callback_answer_failed', err }, 'callback not answered');
    }
  });

  // Последний обработчик: всё, что не команда и не кнопка, — реплика помощнику.
  bot.on('message_created', async (ctx) => {
    // В группах, куда бота добавили, отвечать на каждое сообщение нельзя.
    if (ctx.message.recipient.chat_type !== 'dialog') return;
    const text = ctx.message.body.text?.trim();
    if (!text) {
      await ctx.reply(NON_TEXT_HINT);
      return;
    }
    if (text.startsWith('/')) {
      await ctx.reply(UNKNOWN_COMMAND_TEXT);
      return;
    }
    const sender = ctx.message.sender;
    if (!sender) return;
    await deps.publisher.message({
      max_user_id: sender.user_id,
      chat_id: ctx.message.recipient.chat_id ?? sender.user_id,
      text: text.slice(0, 4000),
      first_name: sender.first_name,
      last_name: sender.last_name ?? null,
      username: sender.username ?? null,
    });
  });
}
