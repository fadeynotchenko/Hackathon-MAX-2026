// Предпросмотр: документ как лист итогового PDF. Сборщик (core.files.docx)
// кладёт каждую строку текста отдельным абзацем Times New Roman, а первую
// строку — заголовком полужирным кеглем крупнее; лист повторяет это, чтобы
// владелец видел файл, а не форму с полями. Лист белый и в тёмной теме: PDF
// у контрагента тоже белый.
//
// Незаполненное место сервер печатает ровно десятью подчёркиваниями (BLANK в
// core.domain.documents) — в черновике оно подсвечено, чтобы пустой реквизит
// не выглядел готовым. Линии другой длины — часть бланка (место для подписи),
// их не подсвечиваем. У пустого шаблона пусто всё, и подсветка превратила бы
// лист в сплошную ошибку, поэтому там её нет (`marks={false}`).
const BLANK = '__________';
const UNDERSCORES = /(_+)/;

function Line({ text, marks }: { text: string; marks: boolean }) {
  if (!marks) return text;
  return text.split(UNDERSCORES).map((part, index) =>
    part === BLANK ? (
      <mark key={index} className="sheet__blank" aria-label="не заполнено">
        {part}
      </mark>
    ) : (
      part
    ),
  );
}

export function DocPreview({
  text,
  marks = true,
  mini = false,
}: {
  text: string;
  marks?: boolean;
  mini?: boolean;
}) {
  const lines = text.split('\n');
  const heading = lines.findIndex((line) => line.trim());
  return (
    <div className={`sheet${mini ? ' sheet--mini' : ''}`}>
      <div
        className="sheet__page"
        role={mini ? undefined : 'document'}
        aria-label={mini ? undefined : 'Предпросмотр документа'}
        aria-hidden={mini || undefined}
      >
        {lines.map((line, index) => (
          <p
            key={index}
            className={index === heading ? 'sheet__line sheet__line--heading' : 'sheet__line'}
          >
            <Line text={line} marks={marks} />
          </p>
        ))}
      </div>
    </div>
  );
}
