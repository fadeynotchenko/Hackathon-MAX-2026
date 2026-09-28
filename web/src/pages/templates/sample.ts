// Свой шаблон из файла-образца («рыбы»): текст файла и места полей в нём.
// Место — фрагмент образца, на котором в новом документе встанет значение;
// неоднозначный фрагмент («______») уточняет текст перед ним в той же строке.
// Поиск мест повторяет сервер (core.domain.places): по нему рисуется
// предпросмотр, а окончательно места проверяет и применяет сервер.
import type { FieldType, Place, Template, TemplateImport, TemplateRequest } from '@/api/client';
import { asKind, type TemplateKind } from '@/lib/format';

import {
  catalogByKey,
  catalogByLabel,
  catalogKeys,
  type EditorDraft,
  type EditorField,
  FIELDS_MAX,
  keyFor,
  makeField,
  marker,
  norm,
  TITLE_MAX,
  toRequest,
} from './editor';

export interface SampleField extends EditorField {
  places: Place[];
}

export interface SampleDraft {
  title: string;
  kind: TemplateKind;
  description: string;
  // Образец DOCX на сервере; у PDF его нет — шаблон будет текстовым.
  fileId: number | null;
  filename: string;
  format: 'docx' | 'pdf';
  // Текст образца, строка на абзац.
  text: string;
  fields: SampleField[];
}

type Span = [begin: number, end: number, key: string];

// Длинные места ищутся первыми, отрезки не пересекаются, before — не часть места.
export function placeSpans(line: string, places: Array<[string, Place]>): Span[] {
  const taken: Span[] = [];
  const ordered = [...places].sort(
    ([, a], [, b]) => (b.before + b.text).length - (a.before + a.text).length,
  );
  for (const [key, place] of ordered) {
    if (!place.text) continue;
    const needle = place.before + place.text;
    for (let at = line.indexOf(needle); at !== -1; at = line.indexOf(needle, at + needle.length)) {
      const begin = at + place.before.length;
      const end = at + needle.length;
      if (taken.every(([s, e]) => end <= s || begin >= e)) taken.push([begin, end, key]);
    }
  }
  return taken.sort(([a], [b]) => a - b);
}

function placesOf(fields: SampleField[]): Array<[string, Place]> {
  return fields.flatMap((field) =>
    field.places.map((place): [string, Place] => [field.key, place]),
  );
}

// Метка бланка по ключу: {{total}} или {{total|words}} — так размечены
// стандартные бланки (core.usecases.documents.builtin).
const KEY_MARKER = /\{\{\s*(\w+)(?:\s*\|\s*([\w:]+))?\s*\}\}/g;
const VARIANT_LABEL: Record<string, string> = {
  words: 'прописью',
  rub: 'рубли',
  rub_words: 'рубли прописью',
  kop: 'копейки',
  long: 'словами',
  day: 'день',
  month: 'месяц',
  year: 'год',
  yy: 'год',
};

function variantLabel(variant: string): string {
  if (variant.startsWith('per:')) return 'за единицу';
  if (variant.startsWith('vat:')) return 'НДС в том числе';
  return VARIANT_LABEL[variant] ?? variant;
}

// Поле стоит в бланке меткой {{key}}: места ему не нужны, а убрать его нельзя —
// метка осталась бы в файле без значения.
export function markedInFile(text: string, key: string): boolean {
  return [...text.matchAll(KEY_MARKER)].some((match) => match[1] === key);
}

// Текст образца с полями по названию: {{Название клиента}} на месте «ООО «Альфа»»,
// {{Сумма, прописью}} на месте метки бланка {{total|words}}.
export function labelText(draft: Pick<SampleDraft, 'text' | 'fields'>): string {
  const places = placesOf(draft.fields);
  const labels = new Map(draft.fields.map((field) => [field.key, field.label]));
  return draft.text
    .split('\n')
    .map((line) => {
      let out = line;
      for (const [begin, end, key] of placeSpans(line, places).reverse()) {
        out = out.slice(0, begin) + marker(labels.get(key) ?? key) + out.slice(end);
      }
      return out.replace(KEY_MARKER, (whole, key: string, variant?: string) => {
        const label = labels.get(key);
        if (!label) return whole;
        return marker(variant ? `${label}, ${variantLabel(variant)}` : label);
      });
    })
    .join('\n');
}

export function placeFound(text: string, place: Place): boolean {
  return text.split('\n').some((line) => line.includes(place.before + place.text));
}

// Поле по названию: уже отмеченное в черновике, готовое из каталога или новое
// своё — с типом, который предложил помощник.
function fieldFor(
  fields: SampleField[],
  label: string,
  taken: Set<string>,
  type: FieldType = 'text',
  required = true,
): SampleField {
  const own = fields.find((field) => norm(field.label) === norm(label));
  if (own) return own;
  const catalog = catalogByLabel(label);
  if (catalog)
    return fields.find((field) => field.key === catalog.key) ?? { ...catalog, places: [] };
  const key = keyFor(label, taken);
  taken.add(key);
  return { ...makeField(key, label, type, { required }), places: [] };
}

function takenKeys(fields: SampleField[]): Set<string> {
  return new Set([...catalogKeys(), ...fields.map((field) => field.key)]);
}

function withPlaces(fields: SampleField[], field: SampleField, places: Place[]): SampleField[] {
  const current = fields.find((item) => item.key === field.key);
  const merged = [...(current?.places ?? field.places)];
  for (const place of places) {
    if (!merged.some((item) => item.text === place.text && item.before === place.before)) {
      merged.push(place);
    }
  }
  const next = { ...(current ?? field), places: merged };
  return current ? fields.map((item) => (item.key === field.key ? next : item)) : [...fields, next];
}

// Ответ разбора файла → черновик. Реквизит из каталога получает название
// каталога: «ИНН» от помощника у продавца и у клиента было бы одинаковым.
export function draftFromImport(result: TemplateImport): SampleDraft {
  let fields: SampleField[] = [];
  const taken = takenKeys(fields);
  for (const imported of result.fields) {
    if (imported.places.length === 0) continue;
    const catalog = imported.key ? catalogByKey(imported.key) : undefined;
    const field = catalog
      ? (fields.find((item) => item.key === catalog.key) ?? { ...catalog, places: [] })
      : fieldFor(fields, imported.label, taken, imported.type, imported.required);
    fields = withPlaces(fields, field, imported.places);
  }
  return {
    title: result.title,
    kind: result.kind,
    description: '',
    fileId: result.file_id ?? null,
    filename: result.filename,
    format: result.format,
    text: result.text,
    fields,
  };
}

// Свой шаблон из файла — на правку; стандартный бланк — копией (свой на его основе).
export function draftFromTemplate(template: Template): SampleDraft {
  return {
    title: template.title,
    kind: asKind(template.kind),
    description: template.description,
    fileId: template.file?.id ?? null,
    filename: template.file?.filename ?? '',
    format: 'docx',
    text: template.file?.text ?? '',
    fields: template.fields.map((field) => ({
      key: field.key,
      label: field.label,
      type: field.type,
      required: field.required,
      hint: field.hint,
      carry_over: field.carry_over,
      today_by_default: field.today_by_default,
      default: field.default ?? '',
      places: field.places ?? [],
    })),
  };
}

export function addPlace(draft: SampleDraft, label: string, place: Place): SampleDraft {
  const field = fieldFor(draft.fields, label, takenKeys(draft.fields));
  return { ...draft, fields: withPlaces(draft.fields, field, [place]) };
}

export function withoutField(draft: SampleDraft, key: string): SampleDraft {
  return { ...draft, fields: draft.fields.filter((field) => field.key !== key) };
}

export function withSampleField(draft: SampleDraft, field: SampleField): SampleDraft {
  return {
    ...draft,
    fields: draft.fields.map((item) => (item.key === field.key ? field : item)),
  };
}

export function sampleProblems(draft: SampleDraft): string[] {
  const problems: string[] = [];
  if (!draft.title.trim()) problems.push('Назовите шаблон');
  if (draft.fields.length === 0) problems.push('Отметьте хотя бы одно место для данных');
  if (draft.fields.length > FIELDS_MAX) problems.push(`Полей — не больше ${FIELDS_MAX}`);
  return problems;
}

// PDF в текстовый редактор: текст с полями по названию, поля — известные.
export function toTextDraft(draft: SampleDraft): EditorDraft {
  return {
    title: draft.title.slice(0, TITLE_MAX),
    kind: draft.kind,
    description: draft.description,
    text: labelText(draft),
    known: draft.fields.map(({ places: _places, ...field }) => field),
  };
}

// DOCX сохраняется образцом с местами, PDF — текстовым шаблоном.
export function sampleRequest(draft: SampleDraft): TemplateRequest {
  if (draft.fileId === null) return toRequest(toTextDraft(draft));
  return {
    title: draft.title.trim(),
    kind: draft.kind,
    description: draft.description.trim(),
    body: '',
    file_id: draft.fileId,
    fields: draft.fields.map((field) => ({
      key: field.key,
      label: field.label,
      type: field.type,
      required: field.required,
      hint: field.hint,
      carry_over: field.carry_over,
      today_by_default: field.today_by_default,
      default: field.default ?? '',
      places: field.places,
    })),
  };
}
