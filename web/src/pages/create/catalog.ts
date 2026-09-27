// Разделы каталога шаблонов во вкладке «Создать».
import type { Template } from '@/api/client';
import { asKind, KIND_ORDER, KIND_STYLE } from '@/lib/format';

// Без своих шаблонов — одна сетка; со своими — разделы по видам документа,
// в каждом стандартный шаблон первым (сервер отдаёт их раньше своих).
export function catalogSections(templates: Template[]): Array<[string, Template[]]> {
  if (!templates.some((template) => !template.is_builtin)) {
    return templates.length > 0 ? [['Шаблоны', templates]] : [];
  }
  return KIND_ORDER.map((kind): [string, Template[]] => [
    KIND_STYLE[kind].section,
    templates.filter((template) => asKind(template.kind) === kind),
  ]).filter(([, list]) => list.length > 0);
}
