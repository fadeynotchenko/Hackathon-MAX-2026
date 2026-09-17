import type { Bot } from '@maxhub/max-bot-api';

import type { BotContext } from '../context.js';
import type { EventPublisher } from '../events/publisher.js';
import type { MainKeyboardOptions } from '../keyboards/main.js';
import type { Logger } from '../logger.js';
import { registerFallback } from './fallback.js';
import { registerHelp } from './help.js';
import { registerProfile } from './profile.js';
import { registerStart } from './start.js';

export interface HandlerDeps {
  publisher: EventPublisher;
  log: Logger;
  keyboard: MainKeyboardOptions;
}

// Порядок регистрации = порядок сопоставления: fallback обязан быть последним.
export function registerHandlers(bot: Bot<BotContext>, deps: HandlerDeps): void {
  registerStart(bot, deps);
  registerHelp(bot, deps.keyboard);
  registerProfile(bot);
  registerFallback(bot, deps.keyboard);
}
