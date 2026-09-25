// /start и bot_started: приветствие, кнопка мини-аппа, событие ядру.
import type { Bot } from '@maxhub/max-bot-api';

import type { BotContext } from '../context.js';
import type { EventPublisher } from '../events/publisher.js';
import type { Logger } from '../logger.js';
import { mainKeyboard, type MainKeyboardOptions } from '../keyboards/main.js';

// Два равноправных входа в одни и те же документы: форма в приложении и
// сообщение сюда. Итог у обоих один — файл приходит в этот чат.
// Разметка — HTML MAX: сообщение уходит с format: 'html'.
export const WELCOME_TEXT = [
  '👋 <b>Привет! Я помощник по документам.</b>',
  '',
  'Подготовлю документ для клиента за пару сообщений — реквизиты вручную набирать не придётся.',
  '',
  '<b>Что умею</b>',
  '🧾 Счёт на оплату',
  '💼 Коммерческое предложение',
  '🤝 Договор оказания услуг',
  '',
  '<b>Как это работает</b>',
  '1️⃣ Расскажите, какой документ нужен',
  '2️⃣ Проверьте, что я записал, и нажмите «Всё верно»',
  '3️⃣ Получите готовый PDF или DOCX прямо в этот чат',
  '',
  '<b>Что можно прислать</b>',
  '✍️ Текст: <i>«Счёт на 120 000 для ООО Ромашка за разработку сайта»</i>',
  '🎙 Голосовое — расшифрую и заполню',
  '📷 Фото карточки предприятия, счёта или договора',
  '📎 Скан в PDF или DOCX',
  '',
  'Удобнее формой? Нажмите «Создать документ» 👇',
  'Все готовые документы — в «Архиве».',
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
    await ctx.reply(WELCOME_TEXT, {
      format: 'html',
      attachments: [mainKeyboard(deps.keyboard)],
    });
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
