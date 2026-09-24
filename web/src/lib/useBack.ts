// «Назад» по истории, а если истории нет (мини-апп открыт ссылкой или
// кнопкой бота прямо на этом экране) — на понятный родительский экран.
import { useCallback } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

export function useBack(fallback: string): () => void {
  const navigate = useNavigate();
  const location = useLocation();
  const hasHistory = location.key !== 'default';
  return useCallback(() => {
    if (hasHistory) {
      void navigate(-1);
    } else {
      void navigate(fallback, { replace: true });
    }
  }, [hasHistory, navigate, fallback]);
}
