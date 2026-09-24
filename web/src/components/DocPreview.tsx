// Предпросмотр: текст документа как его соберёт шаблонизатор. Незаполненное
// место сервер печатает ровно десятью подчёркиваниями (BLANK в
// core.domain.documents) — здесь оно подсвечено, чтобы пустой реквизит не
// выглядел готовым. Линии другой длины — часть бланка (место для подписи), их
// не подсвечиваем.
const BLANK = '__________';
const UNDERSCORES = /(_+)/;

export function DocPreview({ text }: { text: string }) {
  const parts = text.split(UNDERSCORES);
  return (
    <pre className="paper" aria-label="Предпросмотр документа">
      {parts.map((part, index) =>
        part === BLANK ? (
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
