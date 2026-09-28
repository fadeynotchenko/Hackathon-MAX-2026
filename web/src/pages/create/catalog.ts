// Разделы каталога шаблонов во вкладке «Создать».
import type { Template } from '@/api/client';

// Свои шаблоны — отдельной сеткой над стандартными: свой бланк человек сделал
// под себя и ищет прежде всего его, а среди стандартных он терялся. Порядок
// внутри раздела — как отдал сервер. Пустой раздел не показываем: заголовок
// без карточек (нет своих шаблонов, поиск ничего не нашёл) только путает.
export function catalogSections(templates: Template[]): Array<[string, Template[]]> {
  const sections: Array<[string, Template[]]> = [
    ['Мои шаблоны', templates.filter((template) => !template.is_builtin)],
    ['Стандартные', templates.filter((template) => template.is_builtin)],
  ];
  return sections.filter(([, list]) => list.length > 0);
}
