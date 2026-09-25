// Разметка сообщений ядра с кнопками. Нажатие кнопки снимает её с сообщения, а
// снять кнопки MAX позволяет только переотправкой текста. В апдейте нажатия текст
// приходит без HTML (разметка — отдельным списком смещений), и без сохранённого
// оригинала сообщение теряло бы жирный шрифт после первого же нажатия.
import type { Redis } from 'ioredis';

const KEY = 'messages:markup:';
// Кнопку нажимают и через несколько дней; дольше неделю не храним.
const TTL_SECONDS = 7 * 24 * 3600;

export interface FormattedText {
  text: string;
  format: 'markdown' | 'html';
}

export async function rememberMarkup(
  redis: Pick<Redis, 'set'>,
  mid: string,
  value: FormattedText,
): Promise<void> {
  await redis.set(`${KEY}${mid}`, JSON.stringify(value), 'EX', TTL_SECONDS);
}

export async function recallMarkup(
  redis: Pick<Redis, 'get'>,
  mid: string,
): Promise<FormattedText | null> {
  const raw = await redis.get(`${KEY}${mid}`);
  if (!raw) return null;
  try {
    const value = JSON.parse(raw) as Partial<FormattedText>;
    if (typeof value.text !== 'string') return null;
    if (value.format !== 'html' && value.format !== 'markdown') return null;
    return { text: value.text, format: value.format };
  } catch {
    return null;
  }
}
