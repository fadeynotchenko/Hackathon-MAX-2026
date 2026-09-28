// Разделы каталога шаблонов во вкладке «Создать».
import type { Template } from '@/api/client';
import { asKind, KIND_ORDER, KIND_STYLE } from '@/lib/format';

// Свои шаблоны — отдельной сеткой над стандартными: свой бланк человек сделал
// под себя и ищет прежде всего его, а среди стандартных он терялся. Стандартные
// одной сеткой, пока в каждом виде по одному бланку; как только вид повторяется
// (варианты договора и счёта) — разделы по видам. Порядок внутри раздела — как
// отдал сервер. Пустой раздел не показываем: заголовок без карточек (нет своих
// шаблонов, поиск ничего не нашёл) только путает. Делить ли по видам, решает
// весь каталог, а не выдача поиска: иначе заголовки менялись бы от запроса.
export function catalogSections(
  templates: Template[],
  catalog: Template[] = templates,
): Array<[string, Template[]]> {
  const own = templates.filter((template) => !template.is_builtin);
  const standard = templates.filter((template) => template.is_builtin);
  const sections: Array<[string, Template[]]> = [['Мои шаблоны', own]];
  const kinds = catalog
    .filter((template) => template.is_builtin)
    .map((template) => asKind(template.kind));
  if (new Set(kinds).size === kinds.length) {
    sections.push(['Стандартные', standard]);
  } else {
    for (const kind of KIND_ORDER) {
      sections.push([
        KIND_STYLE[kind].section,
        standard.filter((template) => asKind(template.kind) === kind),
      ]);
    }
  }
  return sections.filter(([, list]) => list.length > 0);
}
