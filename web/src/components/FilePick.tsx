// Выбор фото или скана: на телефоне открывает камеру или галерею, на десктопе —
// диалог файла. Типы — те, что распознаёт сервер (фото, PDF, DOCX).
import { CellSimple, Spinner } from '@maxhub/max-ui';
import { useRef, type ReactNode } from 'react';

const RECOGNIZABLE =
  'image/jpeg,image/png,image/webp,image/bmp,image/tiff,application/pdf,' +
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document';

export interface FilePickProps {
  title: string;
  subtitle?: string | undefined;
  icon: ReactNode;
  busy?: boolean | undefined;
  // Что писать, пока файл обрабатывается.
  busyTitle?: string | undefined;
  // Типы файлов для диалога; по умолчанию — всё, что распознаёт сервер.
  accept?: string | undefined;
  onPick: (file: File) => void;
}

export function FilePick({
  title,
  subtitle,
  icon,
  busy,
  busyTitle = 'Распознаём…',
  accept = RECOGNIZABLE,
  onPick,
}: FilePickProps) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <>
      <CellSimple
        title={busy ? busyTitle : title}
        subtitle={subtitle}
        before={
          <span className="themed-icon">
            {busy ? <Spinner size={24} appearance="themed" /> : icon}
          </span>
        }
        disabled={Boolean(busy)}
        showChevron
        onClick={() => input.current?.click()}
      />
      <input
        ref={input}
        type="file"
        accept={accept}
        hidden
        onChange={(event) => {
          const file = event.target.files?.[0];
          event.target.value = '';
          if (file) onPick(file);
        }}
      />
    </>
  );
}
