// Поле формы на компонентах MAX UI: подпись, ввод, источник значения и ошибка
// рядом с полем. Тип ввода (дата, сумма, цифры) берётся из типа поля шаблона.
// Пример значения и «необязательно» живут в пустом поле плейсхолдером, а не
// отдельной строкой: форма короче, а подсказка исчезает, как только она не нужна.
// Модификатор однострочное/многострочное — для широкого экрана: там однострочные
// поля встают по два в ряд, а адрес и длинный текст занимают всю строку.
// Позиции счёта — своя таблица строк (ItemsInput) с тем же видом подписи и ошибки.
// Поле с подсказками (название, ИНН, банк, адрес) открывает под собой список из
// реестра (Suggestions).
// Реквизит (ИНН, КПП, ОГРН, БИК, счёт) проверяется здесь же, когда человек уходит
// с поля: ошибка сервера, если она есть, важнее.
import { Input, Textarea, Typography } from '@maxhub/max-ui';
import { useId, useState } from 'react';

import type { FieldType } from '@/api/client';
import { inputKind } from '@/lib/format';
import { requisiteProblem } from '@/lib/requisites';

import { ItemsInput } from './ItemsInput';
import { useSuggestions, type SuggestSource } from './Suggestions';

export interface FieldInputProps {
  label: string;
  type: FieldType;
  value: string;
  onChange: (value: string) => void;
  required?: boolean | undefined;
  hint?: string | undefined;
  placeholder?: string | undefined;
  error?: string | null | undefined;
  // Предел длины с сервера: лишнее не набирается, а не отклоняется после отправки.
  maxLength?: number | null | undefined;
  // Откуда значение: «Из организации», «С фото — проверьте».
  source?: { label: string; draft: boolean } | null | undefined;
  suggest?: SuggestSource | undefined;
}

export function FieldInput({
  label,
  type,
  value,
  onChange,
  required,
  hint,
  placeholder,
  error,
  source,
  maxLength,
  suggest,
}: FieldInputProps) {
  const id = useId();
  const kind = inputKind(type);
  const [left, setLeft] = useState(false);
  const suggestions = useSuggestions(type === 'items' ? undefined : suggest);
  if (type === 'items') {
    return (
      <ItemsInput
        label={label}
        value={value}
        onChange={onChange}
        hint={hint}
        error={error}
        source={source}
      />
    );
  }
  const shown = error || (left ? requisiteProblem(type, value) : null);
  const describedBy = shown || hint ? `${id}-note` : undefined;
  // У поля даты плейсхолдера не видно — «необязательно» остаётся в подписи.
  const optionalInLabel = required === false && kind.type === 'date';
  const shownPlaceholder =
    placeholder ?? (required === false && !optionalInLabel ? 'Необязательно' : undefined);
  const common = {
    id,
    value,
    'aria-invalid': Boolean(shown),
    'aria-describedby': describedBy,
    ...(shownPlaceholder ? { placeholder: shownPlaceholder } : {}),
    ...(maxLength ? { maxLength } : {}),
    ...suggestions.inputProps,
    onBlur: () => {
      setLeft(true);
      suggestions.close?.();
    },
  };
  const change = (next: string) => {
    onChange(next);
    suggestions.onType(next);
  };

  return (
    <div
      className={`field ${kind.multiline ? 'field--multiline' : 'field--single'}${shown ? ' field--error' : ''}`}
    >
      <div className="field__label">
        <Typography.Text variant="description-strong" color="secondary" asChild>
          <label htmlFor={id}>
            {label}
            {optionalInLabel ? ' · необязательно' : ''}
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
      <div className={`field__control${suggest ? ' field__control--suggest' : ''}`}>
        {kind.multiline ? (
          <Textarea
            {...common}
            mode="secondary"
            className="field__box"
            rows={3}
            onChange={(event) => change(event.target.value)}
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
            onChange={(event) => change(event.target.value)}
          />
        )}
        {suggestions.list}
      </div>
      {shown ? (
        <Typography.Text
          id={describedBy}
          variant="description"
          className="field__note field__error"
        >
          {shown}
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
