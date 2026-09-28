// «Назад» по истории, если под экраном в стеке есть прежний; если экран открыт
// первым (ссылкой или кнопкой бота прямо на нём) — на понятный родительский
// экран. Ключ записи истории для этого не годится: мини-апп заменяет корневую
// запись экраном из параметра запуска, и ключ уже не «default», а шаг назад
// уводил в пустоту — системная стрелка MAX ничего не делала.
import { useCallback } from 'react';
import { useNavigate } from 'react-router-dom';

import { useScreenActivity } from './screenMemory';

export function useBack(fallback: string): () => void {
  const navigate = useNavigate();
  const { canGoBack } = useScreenActivity();
  return useCallback(() => {
    if (canGoBack) {
      void navigate(-1);
    } else {
      void navigate(fallback, { replace: true });
    }
  }, [canGoBack, navigate, fallback]);
}
