// Ответ на кнопку «Профиль»: то, что бот знает о пользователе из апдейта и сессии.
import type { Bot } from '@maxhub/max-bot-api';

import type { BotContext } from '../context.js';
import { CALLBACKS } from '../keyboards/main.js';

export function profileText(ctx: BotContext): string {
  const user = ctx.user;
  if (!user) return 'Не удалось определить пользователя.';
  const lines = [
    `Имя: ${[user.first_name, user.last_name].filter(Boolean).join(' ')}`,
    `ID в MAX: ${user.user_id}`,
  ];
  if (user.username) lines.push(`Username: @${user.username}`);
  if (ctx.session?.starts) lines.push(`Запусков бота: ${ctx.session.starts}`);
  return lines.join('\n');
}

export function registerProfile(bot: Bot<BotContext>): void {
  bot.action(CALLBACKS.profile, async (ctx) => {
    await ctx.answerOnCallback({ message: { text: profileText(ctx) } });
  });
}
