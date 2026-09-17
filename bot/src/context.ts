import type { SessionContext } from '@maxhub/max-bot-api';

// Состояние пользователя между апдейтами (Redis, TTL — BOT_SESSION_TTL_SECONDS).
export interface BotSession {
  starts: number;
  firstSeenAt?: string;
  lastSeenAt?: string;
}

export type BotContext = SessionContext<BotSession>;
