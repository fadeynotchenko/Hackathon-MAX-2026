// Защита прода от локального стенда с тем же токеном бота.
//
// SDK в polling-режиме при старте снимает ВСЕ вебхук-подписки бота. Если тот же
// токен обслуживает прод на домене, `docker compose up` на ноутбуке молча
// отключал бы его: апдейты перестают доходить до прода, ошибок нет ни в одном
// логе, а прод-бот подписывается заново только при своём рестарте.
import type { Api } from '@maxhub/max-bot-api';

/** Адреса вебхуков, которые снял бы запуск polling; пустой список — мешать некому. */
export async function webhooksInTheWay(
  api: Pick<Api, 'getSubscriptions'>,
  takeover: boolean,
): Promise<string[]> {
  if (takeover) return [];
  // Без поля subscriptions в ответе SDK возвращает undefined, а не пустой массив.
  const subscriptions = (await api.getSubscriptions()) ?? [];
  return subscriptions.map((subscription) => subscription.url);
}
