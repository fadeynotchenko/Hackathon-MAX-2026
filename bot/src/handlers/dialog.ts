// Диалог с помощником: текст, вложения и нажатия кнопок документов уходят в
// ядро, ответ приходит событием notify.user. Бот здесь только канал: модель,
// документы и права живут в ядре, поэтому тот же диалог работает и из мини-аппа.
import type { Bot } from '@maxhub/max-bot-api';

import type { BotContext } from '../context.js';
import type { BotAttachment } from '../events/codec.js';
import type { EventPublisher } from '../events/publisher.js';
import type { Logger } from '../logger.js';

export const DOC_ACTION = /^doc:/;
export const NON_TEXT_HINT =
  'Я понимаю текст, голосовые, фото и сканы (PDF, DOCX). Напишите, какой документ нужен, например: «Счёт на 50 000 для ООО Ромашка за консультацию».';
export const UNKNOWN_COMMAND_TEXT =
  'Такой команды нет. Наберите /help или просто напишите, что нужно.';

export interface DialogDeps {
  publisher: EventPublisher;
  log: Logger;
}

// Вложение из апдейта MAX в том виде, который нужен здесь: SDK не экспортирует
// сырые типы вложений, а разбирать нужно только тип, ссылку и имя файла.
interface RawAttachment {
  type: string;
  payload?: unknown;
  filename?: string;
  size?: number;
}

export type PickedAttachment = Pick<BotAttachment, 'kind' | 'url' | 'filename' | 'size'>;

// Первое вложение, которое помощник умеет прочитать: фото, файл или голосовое.
// Стикеры, геометки и контакты не годятся — на них бот отвечает подсказкой.
export function pickAttachment(
  attachments: readonly RawAttachment[] | null | undefined,
): PickedAttachment | null {
  for (const item of attachments ?? []) {
    if (item.type !== 'image' && item.type !== 'file' && item.type !== 'audio') continue;
    const url = (item.payload as { url?: unknown } | null | undefined)?.url;
    if (typeof url !== 'string' || !url.startsWith('https://')) continue;
    return {
      kind: item.type,
      url,
      filename: typeof item.filename === 'string' ? item.filename.slice(0, 255) : null,
      size: typeof item.size === 'number' ? item.size : null,
    };
  }
  return null;
}

// «Печатает…» на время, пока ядро думает: распознавание фото занимает секунды.
async function showTyping(
  ctx: { sendAction?: (action: 'typing_on') => Promise<unknown> },
  log: Logger,
): Promise<void> {
  try {
    await ctx.sendAction?.('typing_on');
  } catch (err) {
    log.warn({ event: 'dialog.typing_failed', err }, 'typing indicator not shown');
  }
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
    const text = ctx.message.body.text?.trim() ?? '';
    const sender = ctx.message.sender;
    const attachment = pickAttachment(ctx.message.body.attachments);
    if (attachment && sender) {
      // Текст рядом с фото — подпись к нему («это покупатель»), а не отдельная реплика.
      await showTyping(ctx, deps.log);
      await deps.publisher.attachment({
        max_user_id: sender.user_id,
        chat_id: ctx.message.recipient.chat_id ?? sender.user_id,
        ...attachment,
        text: text ? text.slice(0, 4000) : null,
        first_name: sender.first_name,
        last_name: sender.last_name ?? null,
        username: sender.username ?? null,
      });
      return;
    }
    if (!text) {
      await ctx.reply(NON_TEXT_HINT);
      return;
    }
    if (text.startsWith('/')) {
      await ctx.reply(UNKNOWN_COMMAND_TEXT);
      return;
    }
    if (!sender) return;
    await showTyping(ctx, deps.log);
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
