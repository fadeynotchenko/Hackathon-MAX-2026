// Счётчик шагов документа. Шагов всегда три и они одни на все способы
// заполнения (форма, чат, фото, голос): данные → проверка → экспорт.
import { Typography } from '@maxhub/max-ui';

const DOCUMENT_STEPS = ['Данные', 'Проверка', 'Экспорт'] as const;

export function Steps({ current }: { current: 1 | 2 | 3 }) {
  return (
    <div className="steps" aria-label={`Шаг ${current} из 3`}>
      <div className="steps__bar">
        {DOCUMENT_STEPS.map((step, index) => (
          <span
            key={step}
            className={`steps__segment${index < current ? ' steps__segment--done' : ''}`}
          />
        ))}
      </div>
      <Typography.Text variant="label" color="tertiary">
        Шаг {current} из 3 · {DOCUMENT_STEPS[current - 1]}
      </Typography.Text>
    </div>
  );
}
