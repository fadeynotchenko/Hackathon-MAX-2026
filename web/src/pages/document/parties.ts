// Стороны документа из формы: клиент — из карточек, «От кого» — из своих
// организаций. Выбор уходит на сервер сразу (реквизиты стороны встают целиком),
// и экран выбора возвращает в форму с плашкой — тем же ходом, что экраны
// способов заполнения: плашка в памяти (fillMethods.ts), «Назад» по истории.
//
// «Новый клиент» и «Новая организация» заменяют выбор формой профиля, а та
// после сохранения заменяет себя выбором с id новой записи в state: выбор
// подставляет её сразу. История так и остаётся [форма, выбор] — шаг назад ведёт
// в форму документа; при обычном переходе вперёд между ними остался бы прежний
// экран выбора. Передумал заводить запись — «Назад» тоже ведёт в форму.
import { useEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';

import { useAuth } from '@/auth/context';
import { errorText } from '@/lib/useAsync';
import { useBack } from '@/lib/useBack';
import { hapticResult } from '@/max/webapp';

import { fillFormPath, leaveNotice, type FillNotice } from './fillMethods';

type PartySide = 'client' | 'seller';

export function partyPickPath(documentId: number, side: PartySide): string {
  return `${fillFormPath(documentId)}/${side}`;
}

// Ключ id новой записи в state возврата: так его кладут формы профиля.
const CREATED_KEY = { client: 'counterpartyId', seller: 'organizationId' } as const;

function applied(side: PartySide, id: number | null): FillNotice {
  if (id === null) return { tone: 'info', title: 'Реквизиты из карточки убраны' };
  return {
    tone: 'success',
    title:
      side === 'client' ? 'Реквизиты клиента подставлены' : 'Реквизиты организации подставлены',
  };
}

interface PartyPick {
  busy: boolean;
  // Выбранная строка, пока выбор уходит на сервер: отмечена сразу, не после ответа.
  pending: number | null | undefined;
  error: string | null;
  back: () => void;
  pick: (id: number | null, current: number | null) => Promise<void>;
}

export function usePartyPick(documentId: number, side: PartySide): PartyPick {
  const { api } = useAuth();
  const location = useLocation();
  const back = useBack(fillFormPath(documentId));
  const [pending, setPending] = useState<number | null | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);
  // Второй тап может прийти раньше перерисовки с busy; radio в строке и сама
  // строка тоже зовут pick вместе.
  const running = useRef(false);
  // Ушли с экрана, пока выбор летел, — назад второй раз не шагаем.
  const mounted = useRef(false);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const pick = async (id: number | null, current: number | null) => {
    if (running.current) return;
    running.current = true;
    // Та же сторона заново затёрла бы набранное по ней руками — просто назад.
    if (id === current) {
      back();
      return;
    }
    setPending(id);
    setError(null);
    try {
      await api.setParties(
        documentId,
        side === 'client' ? { counterparty_id: id } : { organization_id: id },
      );
      if (!mounted.current) return;
      hapticResult('success');
      leaveNotice(documentId, applied(side, id));
      // running не снимается: экран уходит.
      back();
    } catch (err) {
      if (!mounted.current) return;
      hapticResult('error');
      setError(errorText(err, 'Не удалось подставить реквизиты'));
      setPending(undefined);
      running.current = false;
    }
  };

  // Вернулись из формы новой записи — подставляем её один раз (ref переживает
  // двойной эффект StrictMode).
  const created = (location.state as Partial<Record<string, number>> | null)?.[CREATED_KEY[side]];
  const autoPicked = useRef(false);
  useEffect(() => {
    if (created === undefined || autoPicked.current) return;
    autoPicked.current = true;
    void pick(created, null);
    // pick стабилен по смыслу: документ и сторона на экране не меняются.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [created]);

  return { busy: pending !== undefined, pending, error, back, pick };
}
