// Строка поиска над списком: одна на все экраны, чтобы поиск выглядел и
// очищался везде одинаково.
import { Icon16SearchOutline, Input } from '@maxhub/max-ui';

export function SearchField({
  value,
  onChange,
  hint,
}: {
  value: string;
  onChange: (value: string) => void;
  hint: string;
}) {
  return (
    <div className="section">
      <Input
        type="search"
        aria-label={hint}
        placeholder={hint}
        mode="contrast"
        iconBefore={<Icon16SearchOutline />}
        withClearButton
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </div>
  );
}
