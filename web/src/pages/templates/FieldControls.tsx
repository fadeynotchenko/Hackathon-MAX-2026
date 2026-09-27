// Общие части редакторов своего шаблона: каталог полей кнопками и настройка
// поля — тип и обязательность. Ими пользуются редактор текста и экран шаблона
// из файла-образца.
import { Button, Switch, Typography } from '@maxhub/max-ui';
import { useState, type ReactNode } from 'react';

import { FieldInput } from '@/components/FieldInput';

import {
  CUSTOM_TYPES,
  type EditorField,
  FIELD_CATALOG,
  hasFixedType,
  LABEL_MAX,
  sourceText,
  TYPE_LABEL,
} from './editor';

export function FieldPicker({
  onInsert,
  customAction = 'Вставить своё поле',
}: {
  onInsert: (label: string) => void;
  customAction?: string;
}) {
  const [custom, setCustom] = useState('');
  // Фигурные скобки и перевод строки сломали бы маркер в тексте.
  const label = custom.replace(/[{}]/g, '').replace(/\s+/g, ' ').trim();
  return (
    <div className="picker">
      <div className="picker__group">
        <FieldInput
          label="Своё поле"
          type="text"
          value={custom}
          maxLength={LABEL_MAX}
          hint="Например: Срок поставки, Адрес доставки"
          onChange={setCustom}
        />
        <Button
          size="medium"
          variant="secondary"
          disabled={!label}
          onClick={() => {
            onInsert(label);
            setCustom('');
          }}
        >
          {customAction}
        </Button>
      </div>
      {FIELD_CATALOG.map((group) => (
        <div key={group.title} className="picker__group" role="group" aria-label={group.title}>
          <Typography.Text variant="description-strong" color="secondary">
            {group.title}
          </Typography.Text>
          <div className="chips chips--wrap">
            {group.items.map((item) => (
              <Button
                key={item.field.key}
                size="small"
                variant="secondary"
                aria-label={`Вставить «${item.field.label}»`}
                onClick={() => onInsert(item.field.label)}
              >
                {item.short}
              </Button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

export function FieldSettings<T extends EditorField>({
  field,
  onChange,
  children,
}: {
  field: T;
  onChange: (field: T) => void;
  children?: ReactNode;
}) {
  const source = sourceText(field.key);
  const details = [
    TYPE_LABEL[field.type],
    source ? `подставится ${source}` : null,
    field.today_by_default ? 'сегодняшняя по умолчанию' : null,
  ].filter(Boolean);
  return (
    <div className="template-field">
      <div className="template-field__head">
        <div className="template-field__titles">
          <Typography.Text variant="body-strong">{field.label}</Typography.Text>
          <Typography.Text variant="description" color="tertiary">
            {details.join(' · ')}
          </Typography.Text>
        </div>
        <label className="template-field__required">
          <Typography.Text variant="description" color="secondary">
            Обязательное
          </Typography.Text>
          <Switch
            checked={field.required}
            aria-label={`«${field.label}» обязательное`}
            onChange={(event) => onChange({ ...field, required: event.target.checked })}
          />
        </label>
      </div>
      {hasFixedType(field.key) ? null : (
        <div className="chips chips--inset" role="group" aria-label={`Тип поля «${field.label}»`}>
          {CUSTOM_TYPES.map((type) => (
            <Button
              key={type}
              size="small"
              variant={field.type === type ? 'primary' : 'secondary'}
              aria-pressed={field.type === type}
              onClick={() =>
                onChange({
                  ...field,
                  type,
                  today_by_default: type === 'date' && field.today_by_default,
                })
              }
            >
              {TYPE_LABEL[type]}
            </Button>
          ))}
        </div>
      )}
      {children}
    </div>
  );
}
