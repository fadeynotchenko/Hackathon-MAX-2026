// Шаги документа. Шагов всегда три и они одни на все способы заполнения
// (форма, чат, фото, голос): данные → проверка → отправка. Полоска с подписью
// под каждым отрезком: видно и где вы, и что впереди, без строки «Шаг 1 из 3».
const DOCUMENT_STEPS = ['Данные', 'Проверка', 'Отправка'] as const;

export function Steps({ current }: { current: 1 | 2 | 3 }) {
  return (
    <ol className="steps" aria-label={`Шаг ${current} из 3`}>
      {DOCUMENT_STEPS.map((step, index) => {
        const state = index + 1 < current ? 'done' : index + 1 === current ? 'current' : 'next';
        return (
          <li
            key={step}
            className={`steps__item steps__item--${state}`}
            aria-current={state === 'current' ? 'step' : undefined}
          >
            {step}
          </li>
        );
      })}
    </ol>
  );
}
