// Заполнить форму за человека — с фото, голосом или текстом, как в чате с
// ботом: у каждого способа свой экран, итог у всех один. Что-то заполнилось —
// возврат в форму с плашкой «Заполнено N полей»; ничего — человек остаётся на
// экране способа с ответом помощника и пробует ещё раз.
//
// Плашку для формы экран способа оставляет здесь, в памяти: navigate(-1) не
// несёт state, а новый переход вперёд задвоил бы форму в истории. Сами
// значения не передаются — форма при входе перечитывает документ с сервера.
// Ушёл человек «Назад», не дождавшись ответа, — ответ экран уже не трогает:
// значения сервер сохранит, форма покажет их при следующем входе.
import { useEffect, useRef, useState } from 'react';

import type { AgentFillResponse, VoiceFillResponse } from '@/api/client';
import { pluralize } from '@/lib/format';
import { errorText } from '@/lib/useAsync';
import { useBack } from '@/lib/useBack';
import { hapticResult } from '@/max/webapp';

import { labelsOf, stripLabel } from './fields';

export type FillMethod = 'photo' | 'voice' | 'text';

export interface FillNotice {
  tone: 'success' | 'error' | 'info';
  title: string;
  text?: string;
}

// Голосовое отвечает тем же, что текст и фото, плюс расшифровкой.
type FillResult = AgentFillResponse & Partial<Pick<VoiceFillResponse, 'transcript'>>;

const FAILURE: Record<FillMethod, string> = {
  photo: 'Не удалось распознать файл',
  voice: 'Не удалось распознать запись',
  text: 'Не удалось заполнить поля',
};

// Длинную расшифровку плашка показывает началом: целиком её не перечитывают.
const TRANSCRIPT_PREVIEW = 200;

export function fillFormPath(documentId: number): string {
  return `/documents/${documentId}/fill`;
}

export function fillMethodPath(documentId: number, method: FillMethod): string {
  return `${fillFormPath(documentId)}/${method}`;
}

const flash = new Map<number, FillNotice>();

export function leaveNotice(documentId: number, notice: FillNotice): void {
  flash.set(documentId, notice);
}

// Чтение и удаление раздельно: в StrictMode React вызывает инициализатор
// состояния дважды, и «прочитать и стереть» в нём потеряло бы плашку.
export function peekNotice(documentId: number): FillNotice | null {
  return flash.get(documentId) ?? null;
}

export function dropNotice(documentId: number): void {
  flash.delete(documentId);
}

function heard(transcript: string | undefined): string | null {
  const text = transcript?.trim();
  if (!text) return null;
  const preview =
    text.length > TRANSCRIPT_PREVIEW ? `${text.slice(0, TRANSCRIPT_PREVIEW).trimEnd()}…` : text;
  return `Помощник расслышал: «${preview}».`;
}

// Отклонённых значений в документе нет (сервер оставил прежние), и после
// возврата форма их ошибок не покажет — поэтому они названы в плашке.
function rejectedLine(result: FillResult): string | null {
  if (result.rejected.length === 0) return null;
  const items = result.rejected.map((error) => {
    const [label] = labelsOf(result.document, [error.key]);
    return `${label ?? error.key} — ${stripLabel(error.message)}`;
  });
  return `Не записали: ${items.join('; ')}.`;
}

function joined(lines: Array<string | null>): string | undefined {
  const text = lines.filter(Boolean).join(' ');
  return text || undefined;
}

export function filledNotice(result: FillResult): FillNotice {
  const count = result.filled.length;
  const text = joined([heard(result.transcript), rejectedLine(result)]);
  return {
    tone: 'success',
    title: `Заполнено ${count} ${pluralize(count, 'поле', 'поля', 'полей')} — проверьте`,
    ...(text ? { text } : {}),
  };
}

// Ничего не записано: ответ помощника объясняет, чего не нашлось и чего не хватает.
export function emptyNotice(result: FillResult): FillNotice {
  const text = joined([heard(result.transcript), result.reply.trim() || null]);
  return { tone: 'info', title: 'Ничего не заполнено', ...(text ? { text } : {}) };
}

interface FillSubmit {
  busy: boolean;
  notice: FillNotice | null;
  back: () => void;
  submit: (run: () => Promise<FillResult>) => Promise<void>;
}

// Общий ход для трёх экранов: запрос, плашка, возврат в форму. «Назад» — по
// истории, если пришли из формы, иначе заменой на форму.
export function useFillSubmit(documentId: number, method: FillMethod): FillSubmit {
  const back = useBack(fillFormPath(documentId));
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<FillNotice | null>(null);
  // «Назад» доступен и во время запроса. Если экран уже закрыт, человек стоит
  // в форме, прочитавшей документ до ответа: плашка залежалась бы до следующего
  // входа, а back() — navigate(-1) работает и после размонтирования — увёл бы
  // его ещё на шаг назад, мимо формы.
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const submit = async (run: () => Promise<FillResult>) => {
    setBusy(true);
    setNotice(null);
    try {
      const result = await run();
      if (!mounted.current) return;
      if (result.filled.length > 0) {
        hapticResult('success');
        leaveNotice(documentId, filledNotice(result));
        // busy не снимается: экран уходит, повторное нажатие отправило бы файл дважды.
        back();
        return;
      }
      hapticResult('warning');
      setNotice(emptyNotice(result));
    } catch (err) {
      if (!mounted.current) return;
      hapticResult('error');
      setNotice({ tone: 'error', title: errorText(err, FAILURE[method]) });
    }
    setBusy(false);
  };

  return { busy, notice, back, submit };
}
