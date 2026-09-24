// Предпросмотр: текст документа как его соберёт шаблонизатор. Незаполненное
// место сервер печатает прочерком «__________» — здесь оно подсвечено, чтобы
// пустой реквизит не выглядел готовым.
const BLANK = /(_{4,})/;

export function DocPreview({ text }: { text: string }) {
  const parts = text.split(BLANK);
  return (
    <pre className="paper" aria-label="Предпросмотр документа">
      {parts.map((part, index) =>
        BLANK.test(part) ? (
          <mark key={index} className="paper__blank" aria-label="не заполнено">
            {part}
          </mark>
        ) : (
          part
        ),
      )}
    </pre>
  );
}
