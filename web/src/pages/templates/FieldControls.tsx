// Общие части редакторов своего шаблона: каталог полей кнопками и настройка
// поля — тип и обязательность. Ими пользуются редактор текста и экран шаблона
// из файла-образца.
import { Button, Switch, Typography } from '@maxhub/max-ui';
import { useState, type ReactNode } from 'react';

import { FieldInput } from '@/components/FieldInput';
import { IconPlus } from '@/components/icons';
import { KIND_ORDER, KIND_STYLE, type TemplateKind } from '@/lib/format';

import {
  CUSTOM_TYPES,
  type EditorField,
  FIELD_CATALOG,
  hasFixedType,
  LABEL_MAX,
  marker,
  sourceText,
  TYPE_LABEL,
} from './editor';

// Поля для вставки в текст. Раньше это был список кнопок без объяснения: не
// было ясно, что нажатие вставляет поле и куда. Теперь сверху одна фраза, на
// кнопках «+», после нажатия — подтверждение, а своё поле — в конце, когда
// среди готовых нужного не нашлось.
export function FieldPicker({
  onInsert,
  customAction = 'Вставить своё поле',
}: {
  onInsert: (label: string) => void;
  customAction?: string;
}) {
  const [custom, setCustom] = useState('');
  const [inserted, setInserted] = useState<string | null>(null);
  // Фигурные скобки и перевод строки сломали бы маркер в тексте.
  const label = custom.replace(/[{}]/g, '').replace(/\s+/g, ' ').trim();
  const insert = (value: string) => {
    onInsert(value);
    setInserted(value);
  };
  return (
    <div className="picker">
      <Typography.Text variant="description" color="secondary">
        Нажмите поле — оно встанет в текст там, где курсор. В документе на его месте будет значение.
      </Typography.Text>
      {inserted ? (
        <Typography.Text variant="description" className="picker__done" aria-live="polite">
          Вставили {marker(inserted)}
        </Typography.Text>
      ) : null}
      {FIELD_CATALOG.map((group) => (
        <div key={group.title} className="picker__group" role="group" aria-label={group.title}>
          <div className="picker__title">
            <Typography.Text variant="body-strong">{group.title}</Typography.Text>
            <Typography.Text variant="description" color="tertiary">
              {group.note}
            </Typography.Text>
          </div>
          <div className="chips chips--wrap">
            {group.items.map((item) => (
              <Button
                key={item.field.key}
                size="small"
                variant="secondary"
                iconBefore={<IconPlus size={16} />}
                aria-label={`Вставить «${item.field.label}»`}
                onClick={() => insert(item.field.label)}
              >
                {item.short}
              </Button>
            ))}
          </div>
        </div>
      ))}
      <div className="picker__group">
        <div className="picker__title">
          <Typography.Text variant="body-strong">Своё поле</Typography.Text>
          <Typography.Text variant="description" color="tertiary">
            Если нужного нет выше: срок поставки, адрес доставки
          </Typography.Text>
        </div>
        <FieldInput
          label="Название поля"
          type="text"
          value={custom}
          maxLength={LABEL_MAX}
          onChange={setCustom}
        />
        <Button
          size="medium"
          variant="secondary"
          disabled={!label}
          onClick={() => {
            insert(label);
            setCustom('');
          }}
        >
          {customAction}
        </Button>
      </div>
    </div>
  );
}

// Карточка поля шаблона. Сверху — что за поле, под ним — где оно в файле,
// внизу одна строка действий: «Обязательное» и «Убрать». Прежде переключатель
// стоял рядом с названием, а «Убрать» — рядом с текстом из файла, и на узком
// экране строки слипались.
export function FieldSettings<T extends EditorField>({
  field,
  onChange,
  onRemove,
  children,
}: {
  field: T;
  onChange: (field: T) => void;
  onRemove?: () => void;
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
      <div className="template-field__titles">
        <Typography.Text variant="body-strong">{field.label}</Typography.Text>
        <Typography.Text variant="description" color="tertiary">
          {details.join(' · ')}
        </Typography.Text>
      </div>
      {children}
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
      <div className="template-field__actions">
        <label className="template-field__required">
          <Switch
            checked={field.required}
            aria-label={`«${field.label}» обязательное`}
            onChange={(event) => onChange({ ...field, required: event.target.checked })}
          />
          <Typography.Text variant="body" color="secondary">
            Обязательное
          </Typography.Text>
        </label>
        {onRemove ? (
          <Button
            size="small"
            variant="ghost"
            aria-label={`Убрать поле «${field.label}»`}
            onClick={onRemove}
          >
            Убрать
          </Button>
        ) : null}
      </div>
    </div>
  );
}

// Тип документа, как в макете: по нему свой шаблон находит поиск в каталоге
// («договор», «счёт»), а документы на нём попадают в фильтр архива.
export function KindPicker({
  value,
  onChange,
}: {
  value: TemplateKind;
  onChange: (kind: TemplateKind) => void;
}) {
  return (
    <div className="field">
      <div className="field__label">
        <Typography.Text variant="description-strong" color="secondary">
          Тип документа
        </Typography.Text>
      </div>
      <div className="chips chips--wrap" role="group" aria-label="Тип документа">
        {KIND_ORDER.map((kind) => (
          <Button
            key={kind}
            size="small"
            variant={value === kind ? 'primary' : 'secondary'}
            aria-pressed={value === kind}
            onClick={() => onChange(kind)}
          >
            {KIND_STYLE[kind].short}
          </Button>
        ))}
      </div>
    </div>
  );
}
