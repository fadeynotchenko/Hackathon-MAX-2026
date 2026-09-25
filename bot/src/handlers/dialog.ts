// Диалог с помощником: текст, вложения и нажатия кнопок документов уходят в
// ядро, ответ приходит событием notify.user. Бот здесь только канал: модель,
// документы и права живут в ядре, поэтому тот же диалог работает и из мини-аппа.
import type { Bot } from '@maxhub/max-bot-api';
import type { Redis } from 'ioredis';

import type { BotContext } from '../context.js';
import type { BotAttachment } from '../events/codec.js';
import { recallMarkup } from '../events/markup.js';
import type { EventPublisher } from '../events/publisher.js';
import { mainKeyboard, type MainKeyboardOptions } from '../keyboards/main.js';
import type { Logger } from '../logger.js';
import { WELCOME_TEXT } from './start.js';

export const DOC_ACTION = /^doc:/;
// Разметка — HTML MAX, как у приветствия.
export const NON_TEXT_HINT = [
  '🤔 Такое сообщение я не прочитаю.',
  '',
  'Понимаю текст, голосовые, фото и сканы в PDF или DOCX. Напишите, какой документ нужен, например:',
  '<i>«Счёт на 50 000 для ООО Ромашка за консультацию»</i>',
].join('\n');
export const UNKNOWN_COMMAND_TEXT = [
  '🤷 Такой команды нет.',
  'Наберите /help или просто напишите, что нужно.',
].join('\n');

// «Привет» — не просьба о документе: помощник принял бы его за вопрос о текущем
// документе и ответил бы невпопад. На приветствие бот отвечает сам, как на /start.
const GREETING =
  /^(привет\p{L}*|здравствуй(те)?|здрась?те|добр(ый|ое|ой) (день|утро|вечер|ночи)|хай|салют|hello|hi|hey|start|старт|начать|меню)$/u;

export function isGreeting(text: string): boolean {
  const words = text
    .toLowerCase()
    .replace(/ё/g, 'е')
    .replace(/[^\p{L}\s]/gu, ' ')
    .trim()
    .replace(/\s+/g, ' ');
  return GREETING.test(words);
}

export interface DialogDeps {
  publisher: EventPublisher;
  log: Logger;
  keyboard: MainKeyboardOptions;
  // Разметка отправленных сообщений: с ней снятие кнопок не стирает жирный шрифт.
  redis: Pick<Redis, 'get'>;
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

// Сохранённая разметка нажатого сообщения. Redis недоступен — не повод оставить
// кнопки висеть: сообщение переотправится простым текстом.
async function markupOf(mid: string | undefined, deps: DialogDeps) {
  if (!mid) return null;
  try {
    return await recallMarkup(deps.redis, mid);
  } catch (err) {
    deps.log.warn({ event: 'dialog.markup_unavailable', err }, 'markup not read');
    return null;
  }
}

export function registerDialog(bot: Bot<BotContext>, deps: DialogDeps): void {
  bot.action(DOC_ACTION, async (ctx) => {
    const payload = ctx.callback?.payload;
    const user = ctx.user;
    if (!payload || !user || ctx.chatId === undefined || ctx.chatId === null) return;
    // Сначала снимаем кнопки с нажатого сообщения, потом отдаём нажатие ядру:
    // пока кнопки висят, второе нажатие на «прислать файл» успевает уйти следом.
    // Остальные дубли отсекает ядро.
    const original = ctx.message?.body.text;
    if (original) {
      const formatted = await markupOf(ctx.message?.body.mid, deps);
      try {
        await ctx.answerOnCallback({
          message: formatted
            ? { text: formatted.text, format: formatted.format, attachments: [] }
            : { text: original, attachments: [] },
        });
      } catch (err) {
        deps.log.warn({ event: 'dialog.callback_answer_failed', err }, 'callback not answered');
      }
    }
    await deps.publisher.callback({
      max_user_id: user.user_id,
      chat_id: ctx.chatId,
      payload,
    });
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
      await ctx.reply(NON_TEXT_HINT, { format: 'html' });
      return;
    }
    if (text.startsWith('/')) {
      await ctx.reply(UNKNOWN_COMMAND_TEXT);
      return;
    }
    if (isGreeting(text)) {
      await ctx.reply(WELCOME_TEXT, {
        format: 'html',
        attachments: [mainKeyboard(deps.keyboard)],
      });
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
