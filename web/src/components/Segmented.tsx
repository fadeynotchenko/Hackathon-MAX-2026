// Выбор одного из двух-трёх вариантов плитками в ряд. Внутри — обычные
// радиокнопки: клавиатура, скринридер и клик по подписи работают как у Radio,
// а на экране одна строка вместо списка с пояснениями.
export interface SegmentedOption<T extends string> {
  value: T;
  title: string;
  note?: string;
}

export function Segmented<T extends string>({
  name,
  label,
  options,
  value,
  onChange,
}: {
  name: string;
  label: string;
  options: Array<SegmentedOption<T>>;
  value: T;
  onChange: (value: T) => void;
}) {
  return (
    <div className="segmented" role="radiogroup" aria-label={label}>
      {options.map((option) => (
        <label
          key={option.value}
          className={`segmented__option${option.value === value ? ' segmented__option--active' : ''}`}
        >
          <input
            type="radio"
            className="visually-hidden"
            name={name}
            value={option.value}
            checked={option.value === value}
            onChange={() => onChange(option.value)}
          />
          <span className="segmented__title">{option.title}</span>
          {option.note ? <span className="segmented__note">{option.note}</span> : null}
        </label>
      ))}
    </div>
  );
}
