// Ответ на кнопку «Профиль»: то, что бот знает о пользователе из апдейта и сессии.
import { fmt, type Bot } from '@maxhub/max-bot-api';

import type { BotContext } from '../context.js';
import { CALLBACKS } from '../keyboards/main.js';

// HTML MAX: имя и username приходят от пользователя и экранируются.
export function profileText(ctx: BotContext): string {
  const user = ctx.user;
  if (!user) return '🤔 Не удалось определить пользователя.';
  const name = [user.first_name, user.last_name].filter(Boolean).join(' ');
  const lines = [
    '👤 <b>Профиль</b>',
    '',
    `Имя: <b>${fmt.escapeHtml(name)}</b>`,
    `ID в MAX: <code>${user.user_id}</code>`,
  ];
  if (user.username) lines.push(`Username: @${fmt.escapeHtml(user.username)}`);
  if (ctx.session?.starts) lines.push(`Запусков бота: ${ctx.session.starts}`);
  return lines.join('\n');
}

export function registerProfile(bot: Bot<BotContext>): void {
  bot.action(CALLBACKS.profile, async (ctx) => {
    await ctx.answerOnCallback({ message: { text: profileText(ctx), format: 'html' } });
  });
}
