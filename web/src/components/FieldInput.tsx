// Поле формы на компонентах MAX UI: подпись, ввод, источник значения и ошибка
// рядом с полем. Тип ввода (дата, сумма, цифры) берётся из типа поля шаблона.
import { Input, Textarea, Typography } from '@maxhub/max-ui';
import { useId } from 'react';

import type { FieldType } from '@/api/client';
import { inputKind } from '@/lib/format';

export interface FieldInputProps {
  label: string;
  type: FieldType;
  value: string;
  onChange: (value: string) => void;
  required?: boolean | undefined;
  hint?: string | undefined;
  error?: string | null | undefined;
  // Предел длины с сервера: лишнее не набирается, а не отклоняется после отправки.
  maxLength?: number | null | undefined;
  // Откуда значение: «Из организации», «С фото — проверьте».
  source?: { label: string; draft: boolean } | null | undefined;
}

export function FieldInput({
  label,
  type,
  value,
  onChange,
  required,
  hint,
  error,
  source,
  maxLength,
}: FieldInputProps) {
  const id = useId();
  const kind = inputKind(type);
  const describedBy = error || hint ? `${id}-note` : undefined;
  const common = {
    id,
    value,
    'aria-invalid': Boolean(error),
    'aria-describedby': describedBy,
    ...(maxLength ? { maxLength } : {}),
  };

  return (
    <div className={`field${error ? ' field--error' : ''}`}>
      <div className="field__label">
        <Typography.Text variant="description-strong" color="secondary" asChild>
          <label htmlFor={id}>
            {label}
            {required === false ? ' · необязательно' : ''}
          </label>
        </Typography.Text>
        {source ? (
          <Typography.Text
            variant="description"
            className={`source-tag${source.draft ? ' source-tag--draft' : ''}`}
          >
            {source.label}
          </Typography.Text>
        ) : null}
      </div>
      <div className="field__control">
        {kind.multiline ? (
          <Textarea
            {...common}
            mode="secondary"
            className="field__box"
            rows={3}
            onChange={(event) => onChange(event.target.value)}
          />
        ) : (
          <Input
            {...common}
            className="field__box"
            type={kind.type}
            inputMode={kind.inputMode}
            iconAfter={
              kind.suffix ? (
                <Typography.Text variant="body" color="tertiary">
                  {kind.suffix}
                </Typography.Text>
              ) : undefined
            }
            onChange={(event) => onChange(event.target.value)}
          />
        )}
      </div>
      {error ? (
        <Typography.Text
          id={describedBy}
          variant="description"
          className="field__note field__error"
        >
          {error}
        </Typography.Text>
      ) : hint ? (
        <Typography.Text
          id={describedBy}
          variant="description"
          color="tertiary"
          className="field__note"
        >
          {hint}
        </Typography.Text>
      ) : null}
    </div>
  );
}
