// Поиск по спискам экранов: все слова запроса должны найтись в карточке, в любом
// порядке и регистре. Ищем по всему, что человек помнит о записи, — название,
// ИНН, адрес, подписант, — а не только по заголовку строки: «7736» или «Иванов»
// находят клиента так же, как «Лютик». Буква «ё» приравнена к «е»: в реквизитах
// пишут по-разному, а ищут чаще без неё.
function normalize(text: string): string {
  return text.toLowerCase().replaceAll('ё', 'е');
}

export function matchesQuery(fields: (string | null | undefined)[], query: string): boolean {
  const words = normalize(query).split(/\s+/).filter(Boolean);
  if (words.length === 0) return true;
  const haystack = normalize(fields.filter(Boolean).join(' '));
  return words.every((word) => haystack.includes(word));
}

// Поиск по карточке с реквизитами: название, ИНН и все сохранённые значения.
export function matchesCard(
  card: { name: string; inn: string | null; values: Record<string, string> },
  query: string,
): boolean {
  return matchesQuery([card.name, card.inn, ...Object.values(card.values)], query);
}
