// Теги-фильтры под поиском: «Все» и по одному тегу на значение. Повторное
// нажатие на выбранный тег снимает фильтр — как «Все».
import { Button } from '@maxhub/max-ui';

export interface FilterChipsProps {
  label: string;
  options: ReadonlyArray<{ value: string; title: string }>;
  value: string | null;
  onChange: (value: string | null) => void;
}

export function FilterChips({ label, options, value, onChange }: FilterChipsProps) {
  return (
    <div className="chips" role="group" aria-label={label}>
      <Button
        size="small"
        variant={value === null ? 'primary' : 'secondary'}
        onClick={() => onChange(null)}
      >
        Все
      </Button>
      {options.map((option) => (
        <Button
          key={option.value}
          size="small"
          variant={value === option.value ? 'primary' : 'secondary'}
          onClick={() => onChange(value === option.value ? null : option.value)}
        >
          {option.title}
        </Button>
      ))}
    </div>
  );
}
