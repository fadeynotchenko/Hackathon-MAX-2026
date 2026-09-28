// Версия шаблона для кеша листа-картинки (components/SheetPreview): у шаблона
// нет updated_at, а его бланк меняется вместе с текстом, файлом и полями.
export function templateVersion(template: {
  preview: string;
  fields: ReadonlyArray<{ key: string }>;
  file?: { id: number } | null;
}): string {
  const text = `${template.file?.id ?? ''}|${template.preview}|${template.fields.map((f) => f.key).join(',')}`;
  let hash = 5381;
  for (let index = 0; index < text.length; index += 1) {
    hash = ((hash << 5) + hash + text.charCodeAt(index)) | 0;
  }
  return (hash >>> 0).toString(36);
}
