// Позиции таблицы счёта (поле типа items). Сервер хранит их JSON-строкой
// [{name, quantity, unit, price}] и сам проверяет и считает итог
// (core.domain.documents.parse_items); здесь — разбор для формы и живая сумма,
// чтобы человек видел итог, пока набирает цены.
export interface ItemRow {
  name: string;
  quantity: string;
  unit: string;
  price: string;
}

export const EMPTY_ROW: ItemRow = { name: '', quantity: '1', unit: '', price: '' };

function text(value: unknown): string {
  return typeof value === 'string' || typeof value === 'number' ? String(value) : '';
}

// «1 500,50» и «1500.5» — одно число; пусто или не число — null.
export function toNumber(raw: string): number | null {
  const cleaned = raw.replace(/\s+/g, '').replace(',', '.');
  if (!cleaned) return null;
  const value = Number(cleaned);
  return Number.isFinite(value) ? value : null;
}

// Строки из значения поля. Непрочитанное значение — пустой список: форма
// предложит заполнить таблицу заново, а не упадёт.
export function parseItems(raw: string): ItemRow[] {
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    return [];
  }
  if (!Array.isArray(data)) return [];
  return data
    .filter(
      (entry): entry is Record<string, unknown> => typeof entry === 'object' && entry !== null,
    )
    .map((entry) => ({
      name: text(entry['name']),
      quantity: text(entry['quantity']).replace('.', ','),
      unit: text(entry['unit']),
      price: text(entry['price']),
    }));
}

function isEmpty(row: ItemRow): boolean {
  return !row.name.trim() && !row.price.trim();
}

// Значение поля из строк формы. Пустые строки не уходят; нет ни одной —
// пустое значение, то есть поле не заполнено.
export function serializeItems(rows: readonly ItemRow[]): string {
  const filled = rows.filter((row) => !isEmpty(row));
  if (filled.length === 0) return '';
  return JSON.stringify(
    filled.map((row) => ({
      name: row.name.trim(),
      quantity: row.quantity.trim(),
      unit: row.unit.trim(),
      price: row.price.trim(),
    })),
  );
}

// Сумма строки с округлением до копеек, как на сервере; без цены — null.
export function rowAmount(row: ItemRow): number | null {
  const price = toNumber(row.price);
  const quantity = row.quantity.trim() ? toNumber(row.quantity) : 1;
  if (price === null || quantity === null) return null;
  return Math.round(price * quantity * 100) / 100;
}

export function itemsTotal(rows: readonly ItemRow[]): number {
  return rows.reduce((sum, row) => sum + (rowAmount(row) ?? 0), 0);
}
