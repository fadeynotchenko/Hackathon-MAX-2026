// /start и bot_started: приветствие, кнопка мини-аппа, событие ядру.
import type { Bot } from '@maxhub/max-bot-api';

import type { BotContext } from '../context.js';
import type { EventPublisher } from '../events/publisher.js';
import type { Logger } from '../logger.js';
import { mainKeyboard, type MainKeyboardOptions } from '../keyboards/main.js';

// Два равноправных входа в одни и те же документы: форма в приложении и
// сообщение сюда. Итог у обоих один — файл приходит в этот чат.
export const WELCOME_TEXT = [
  'Привет! Я помогу подготовить документы для клиентов: счёт, коммерческое предложение или договор.',
  '',
  'Нажмите «Создать документ», чтобы выбрать шаблон и заполнить форму.',
  'Или просто напишите, что нужно: «Счёт на 120 000 для ООО Ромашка за разработку сайта».',
  'Подойдёт и голосовое, и фото карточки предприятия — я заполню документ,',
  'покажу значения на проверку и пришлю готовый файл сюда.',
].join('\n');

export interface StartDeps {
  publisher: EventPublisher;
  log: Logger;
  keyboard: MainKeyboardOptions;
}

export function registerStart(bot: Bot<BotContext>, deps: StartDeps): void {
  const greet = async (ctx: BotContext, startPayload: string | null, locale: string | null) => {
    const user = ctx.user;
    ctx.session = {
      ...ctx.session,
      starts: (ctx.session?.starts ?? 0) + 1,
      firstSeenAt: ctx.session?.firstSeenAt ?? new Date().toISOString(),
      lastSeenAt: new Date().toISOString(),
    };
    await ctx.reply(WELCOME_TEXT, { attachments: [mainKeyboard(deps.keyboard)] });
    if (!user || ctx.chatId === undefined || ctx.chatId === null) return;
    // Регистрацию делает ядро по событию: у бота нет доступа к БД, и это намеренно.
    await deps.publisher.userStarted({
      max_user_id: user.user_id,
      chat_id: ctx.chatId,
      first_name: user.first_name,
      last_name: user.last_name ?? null,
      username: user.username,
      language_code: locale,
      start_payload: startPayload,
    });
  };

  bot.on('bot_started', async (ctx) => {
    deps.log.info(
      { event: 'bot.started', user_id: ctx.user.user_id, payload: ctx.startPayload },
      'bot started',
    );
    // user_locale в SDK объявлен пустым enum; на проводе это строка вроде "ru".
    const locale = (ctx.update.user_locale as string | undefined) ?? null;
    await greet(ctx, ctx.startPayload ?? null, locale);
  });
  bot.command('start', async (ctx) => {
    await greet(ctx, null, (ctx.update.user_locale as string | undefined) ?? null);
  });
}
