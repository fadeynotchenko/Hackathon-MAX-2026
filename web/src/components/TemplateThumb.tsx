// Миниатюра бланка в каталоге: схема листа по виду документа (у счёта —
// таблица, у договора — подписи сторон), чтобы виды различались до открытия.
export function TemplateThumb({ kind, large }: { kind: string; large?: boolean }) {
  return (
    <div className={`thumb${large ? ' thumb--large' : ''}`} aria-hidden="true">
      <span className="thumb__line thumb__line--title" />
      <span className="thumb__line thumb__line--mid" />
      <span className="thumb__line thumb__line--short" />
      {kind === 'invoice' ? (
        <div className="thumb__table">
          <span className="thumb__line" />
          <span className="thumb__line" />
          <span className="thumb__line" />
          <span className="thumb__line" />
          <span className="thumb__line" />
          <span className="thumb__line" />
        </div>
      ) : (
        <>
          <span className="thumb__line" />
          <span className="thumb__line" />
          <span className="thumb__line thumb__line--mid" />
        </>
      )}
      <span className="thumb__line" />
      <span className="thumb__line thumb__line--short" />
      {kind === 'contract' ? (
        <div className="thumb__sign">
          <span />
          <span />
        </div>
      ) : null}
    </div>
  );
}
