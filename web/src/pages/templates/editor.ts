// Свой шаблон в редакторе. В тексте поле видно по названию — {{ИНН клиента}},
// а сервер хранит маркер по ключу — {{client_inn}}: по ключу реквизит стороны
// узнаётся и подставляется из организации или карточки клиента. Перевод
// туда и обратно и список полей, собранный по тексту, живут здесь, без React.
import type { FieldType, Template, TemplateRequest } from '@/api/client';

export interface EditorField {
  key: string;
  label: string;
  type: FieldType;
  required: boolean;
  hint: string;
  carry_over: boolean;
  today_by_default: boolean;
}

export interface EditorDraft {
  title: string;
  description: string;
  // Текст с полями по названию: {{Название клиента}}.
  text: string;
  // Поля, которые редактор уже знает: из шаблона и настроенные человеком.
  // Поле, пропавшее из текста, остаётся здесь, чтобы вернуться с настройками.
  known: EditorField[];
}

// Пределы сервера (core.usecases.documents.templates).
export const TITLE_MAX = 64;
export const DESCRIPTION_MAX = 300;
export const TEXT_MAX = 20000;
export const LABEL_MAX = 100;
export const FIELDS_MAX = 50;

function makeField(
  key: string,
  label: string,
  type: FieldType,
  extra: Partial<EditorField> = {},
): EditorField {
  return {
    key,
    label,
    type,
    required: true,
    hint: '',
    carry_over: true,
    today_by_default: false,
    ...extra,
  };
}

// Реквизиты стороны: ключи и типы — как у карточки организации и клиента.
const REQUISITES: Array<[key: string, label: string, type: FieldType]> = [
  ['name', 'Название', 'text'],
  ['inn', 'ИНН', 'inn'],
  ['kpp', 'КПП', 'kpp'],
  ['ogrn', 'ОГРН', 'ogrn'],
  ['address', 'Адрес', 'address'],
  ['director', 'Подписант', 'name'],
  ['bank', 'Банк', 'text'],
  ['bic', 'БИК', 'bic'],
  ['account', 'Расчётный счёт', 'account'],
  ['phone', 'Телефон', 'phone'],
  ['email', 'Почта', 'email'],
];
// У ИП нет КПП, у клиента не всегда есть банк: обязательны только название и ИНН,
// остальное человек включит сам.
const REQUIRED_REQUISITES = new Set(['name', 'inn']);

const SIDES = [
  { prefix: 'seller_', suffix: 'продавца', title: 'Ваша организация', source: 'из организации' },
  { prefix: 'client_', suffix: 'клиента', title: 'Клиент', source: 'из карточки клиента' },
] as const;

export interface CatalogItem {
  // Подпись кнопки внутри раздела: «ИНН», а в тексте — «ИНН клиента».
  short: string;
  field: EditorField;
}

export const FIELD_CATALOG: Array<{ title: string; items: CatalogItem[] }> = [
  {
    title: 'Документ',
    items: [
      {
        short: 'Номер',
        field: makeField('number', 'Номер документа', 'text', { carry_over: false }),
      },
      {
        short: 'Дата',
        field: makeField('date', 'Дата документа', 'date', {
          carry_over: false,
          today_by_default: true,
        }),
      },
      { short: 'Сумма', field: makeField('total', 'Сумма', 'money') },
    ],
  },
  ...SIDES.map((side) => ({
    title: side.title,
    items: REQUISITES.map(([key, label, type]) => ({
      short: label,
      field: makeField(`${side.prefix}${key}`, `${label} ${side.suffix}`, type, {
        required: REQUIRED_REQUISITES.has(key),
      }),
    })),
  })),
];

const CATALOG_FIELDS = FIELD_CATALOG.flatMap((group) => group.items.map((item) => item.field));
const REQUISITE_KEYS = new Set(
  SIDES.flatMap((side) => REQUISITES.map(([key]) => `${side.prefix}${key}`)),
);

// Тип поля из каталога задан заранее: у реквизита стороны — карточкой
// (значение подставится само), у номера, даты и суммы — смыслом поля.
export function hasFixedType(key: string): boolean {
  return REQUISITE_KEYS.has(key) || CATALOG_FIELDS.some((field) => field.key === key);
}

export function sourceText(key: string): string | null {
  return SIDES.find((side) => key.startsWith(side.prefix))?.source ?? null;
}

export const TYPE_LABEL: Record<FieldType, string> = {
  text: 'Текст',
  multiline: 'Длинный текст',
  money: 'Сумма',
  date: 'Дата',
  integer: 'Число',
  phone: 'Телефон',
  email: 'Почта',
  name: 'ФИО',
  address: 'Адрес',
  inn: 'ИНН',
  kpp: 'КПП',
  ogrn: 'ОГРН',
  bic: 'БИК',
  account: 'Расчётный счёт',
};

// Типы, которые человек выбирает своему полю; реквизиты сторон — из каталога.
export const CUSTOM_TYPES: FieldType[] = [
  'text',
  'multiline',
  'money',
  'date',
  'integer',
  'phone',
  'email',
];

// {{Название поля}} в тексте редактора; фигурные скобки и перевод строки
// в название не входят.
const LABEL_MARKER = /\{\{\s*([^{}\n]+?)\s*\}\}/g;
// {{key}} в теле шаблона на сервере (core.domain.documents).
const KEY_MARKER = /\{\{\s*(\w+)\s*\}\}/g;

// «инн  клиента» и «ИНН клиента» — одно поле: название набирают руками.
function norm(label: string): string {
  return label.toLowerCase().replace(/ё/g, 'е').replace(/\s+/g, ' ').trim();
}

export function marker(label: string): string {
  return `{{${label}}}`;
}

export function labelsInText(text: string): string[] {
  const seen = new Map<string, string>();
  for (const match of text.matchAll(LABEL_MARKER)) {
    const label = (match[1] ?? '').replace(/\s+/g, ' ');
    if (!seen.has(norm(label))) seen.set(norm(label), label);
  }
  return [...seen.values()];
}

function findByLabel(fields: EditorField[], label: string): EditorField | undefined {
  const wanted = norm(label);
  return fields.find((field) => norm(field.label) === wanted);
}

const TRANSLIT: Record<string, string> = {
  а: 'a',
  б: 'b',
  в: 'v',
  г: 'g',
  д: 'd',
  е: 'e',
  ё: 'e',
  ж: 'zh',
  з: 'z',
  и: 'i',
  й: 'y',
  к: 'k',
  л: 'l',
  м: 'm',
  н: 'n',
  о: 'o',
  п: 'p',
  р: 'r',
  с: 's',
  т: 't',
  у: 'u',
  ф: 'f',
  х: 'h',
  ц: 'ts',
  ч: 'ch',
  ш: 'sh',
  щ: 'sch',
  ъ: '',
  ы: 'y',
  ь: '',
  э: 'e',
  ю: 'yu',
  я: 'ya',
};

// Ключ своего поля — транслит названия: «Срок поставки» → srok_postavki.
// Такой ключ читает помощник, поэтому он осмысленный, а не f_17. Префиксы
// seller_ и client_ — за реквизитами сторон, своё поле их не получает.
export function keyFor(label: string, taken: ReadonlySet<string>): string {
  const base =
    [...label.toLowerCase()]
      .map((char) => TRANSLIT[char] ?? char)
      .join('')
      .replace(/[^a-z0-9]+/g, '_')
      .replace(/^_+|_+$/g, '')
      .slice(0, 40)
      .replace(/_+$/, '') || 'field';
  const safe = /^[a-z]/.test(base) && !/^(seller|client)_/.test(base) ? base : `f_${base}`;
  let key = safe;
  for (let index = 2; taken.has(key); index += 1) key = `${safe}_${index}`;
  return key;
}

// Поля шаблона по тексту: в порядке появления, с настройками из known или
// каталога; незнакомое название — новое своё поле с типом «текст». Два
// названия одного ключа («Подписант» из стандартного счёта и «Подписант
// продавца» из каталога) — одно поле: значение у них общее.
function resolve(draft: EditorDraft): { fields: EditorField[]; keyByLabel: Map<string, string> } {
  const taken = new Set([
    ...draft.known.map((field) => field.key),
    ...CATALOG_FIELDS.map((field) => field.key),
  ]);
  const fields: EditorField[] = [];
  const keyByLabel = new Map<string, string>();
  for (const label of labelsInText(draft.text)) {
    let field = findByLabel(draft.known, label) ?? findByLabel(CATALOG_FIELDS, label);
    if (!field) {
      field = makeField(keyFor(label, taken), label, 'text');
      taken.add(field.key);
    }
    keyByLabel.set(norm(label), field.key);
    if (!fields.some((item) => item.key === field.key)) fields.push(field);
  }
  return { fields, keyByLabel };
}

export function fieldsOf(draft: EditorDraft): EditorField[] {
  return resolve(draft).fields;
}

// Настройка поля (тип, обязательность) запоминается по названию.
export function withField(draft: EditorDraft, field: EditorField): EditorDraft {
  const others = draft.known.filter((item) => norm(item.label) !== norm(field.label));
  return { ...draft, known: [...others, field] };
}

export function insertText(
  text: string,
  selection: { start: number; end: number },
  insertion: string,
): { text: string; caret: number } {
  const start = Math.max(0, Math.min(selection.start, text.length));
  const end = Math.max(start, Math.min(selection.end, text.length));
  return {
    text: text.slice(0, start) + insertion + text.slice(end),
    caret: start + insertion.length,
  };
}

// Пустой бланк, как его покажет сервер: поле — десять подчёркиваний.
export function previewText(text: string): string {
  return text.replace(LABEL_MARKER, '__________');
}

export function problemsOf(draft: EditorDraft): string[] {
  const problems: string[] = [];
  const fields = fieldsOf(draft);
  if (!draft.title.trim()) problems.push('Назовите шаблон');
  if (!draft.text.trim()) problems.push('Напишите текст шаблона');
  else if (fields.length === 0) problems.push('Вставьте в текст хотя бы одно поле');
  if (fields.length > FIELDS_MAX) problems.push(`Полей в шаблоне — не больше ${FIELDS_MAX}`);
  for (const field of fields) {
    if (field.label.length > LABEL_MAX) {
      problems.push(
        `Название поля «${field.label.slice(0, 20)}…» — не длиннее ${LABEL_MAX} символов`,
      );
    }
  }
  return problems;
}

export function toRequest(draft: EditorDraft): TemplateRequest {
  const { fields, keyByLabel } = resolve(draft);
  const body = draft.text.replace(LABEL_MARKER, (whole, label: string) => {
    const key = keyByLabel.get(norm(label));
    return key ? `{{${key}}}` : whole;
  });
  return {
    title: draft.title.trim(),
    description: draft.description.trim(),
    body,
    fields: fields.map((field) => ({
      key: field.key,
      label: field.label,
      type: field.type,
      required: field.required,
      hint: field.hint,
      carry_over: field.carry_over,
      today_by_default: field.today_by_default,
    })),
  };
}

// Шаблон с сервера → черновик редактора. Копия стандартного шаблона сохраняет
// его ключи: помощник и перенос в копию документа узнают те же поля.
export function draftFromTemplate(template: Template, { copy }: { copy: boolean }): EditorDraft {
  const byKey = new Map(template.fields.map((field) => [field.key, field]));
  const text = template.body.replace(KEY_MARKER, (whole, key: string) => {
    const field = byKey.get(key);
    return field ? marker(field.label) : whole;
  });
  return {
    title: copy ? `${template.title} (копия)`.slice(0, TITLE_MAX) : template.title,
    description: template.description,
    text,
    known: template.fields.map((field) => ({
      key: field.key,
      label: field.label,
      type: field.type,
      required: field.required,
      hint: field.hint,
      carry_over: field.carry_over,
      today_by_default: field.today_by_default,
    })),
  };
}

export const EMPTY_DRAFT: EditorDraft = { title: '', description: '', text: '', known: [] };
