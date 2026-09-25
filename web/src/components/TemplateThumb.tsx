// Миниатюра бланка в каталоге: заголовок и строки для заполнения по виду
// документа (у счёта — сумма, у договора — подписи сторон), чтобы виды
// различались до открытия. Строки — читаемый текст, а не серые полосы: полосы
// выглядели как заглушка загрузки, и каталог казался бесконечно грузящимся.
type Sheet = {
  title: string;
  rows: string[];
  totals?: [string, string][];
  signatures?: [string, string];
};

const SHEETS: Record<string, Sheet> = {
  invoice: {
    title: 'Счёт на оплату',
    rows: ['Поставщик', 'Покупатель', 'Работы, услуги'],
    totals: [
      ['НДС', '₽'],
      ['Итого', '₽'],
    ],
  },
  offer: {
    title: 'Коммерческое предложение',
    rows: ['Кому', 'Состав работ', 'Срок'],
    totals: [['Стоимость', '₽']],
  },
  contract: {
    title: 'Договор',
    rows: ['Исполнитель', 'Заказчик', 'Предмет', 'Стоимость'],
    signatures: ['Исполнитель', 'Заказчик'],
  },
};

const FALLBACK: Sheet = { title: 'Документ', rows: ['Стороны', 'Предмет', 'Условия'] };

export function TemplateThumb({ kind, large }: { kind: string; large?: boolean }) {
  const sheet = SHEETS[kind] ?? FALLBACK;
  return (
    <div className={`thumb${large ? ' thumb--large' : ''}`} aria-hidden="true">
      <span className="thumb__title">{sheet.title}</span>
      <span className="thumb__meta">№ ____ от ____</span>
      {sheet.rows.map((row) => (
        <span key={row} className="thumb__row">
          {row}
          <span className="thumb__blank" />
        </span>
      ))}
      {sheet.totals?.map(([label, unit]) => (
        <span key={label} className="thumb__row thumb__row--total">
          {label}
          <span className="thumb__blank" />
          {unit}
        </span>
      ))}
      {sheet.signatures ? (
        <span className="thumb__sign">
          {sheet.signatures.map((side) => (
            <span key={side}>{side}</span>
          ))}
        </span>
      ) : null}
    </div>
  );
}
