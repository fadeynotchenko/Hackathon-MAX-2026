// Подпись руководителя и печать организации картинками. Их фотографируют на
// белом листе: сервер делает фон прозрачным и ставит картинку в строку подписи
// продавца в документах этой организации (PDF и DOCX).
import { CellAction, CellHeader, CellList, CellSimple } from '@maxhub/max-ui';
import { useEffect, useState } from 'react';

import type { MarkKind, Organization } from '@/api/client';
import { Banner } from '@/components/Banner';
import { FilePick } from '@/components/FilePick';
import { IconCamera, IconTrash } from '@/components/icons';
import { useAuth } from '@/auth/context';
import { errorText } from '@/lib/useAsync';

const PICTURES = 'image/jpeg,image/png,image/webp';

const KINDS: { kind: MarkKind; title: string; has: (org: Organization) => boolean }[] = [
  { kind: 'signature', title: 'Подпись руководителя', has: (org) => org.has_signature },
  { kind: 'stamp', title: 'Печать', has: (org) => org.has_stamp },
];

export function OrganizationMarks({ organization }: { organization: Organization }) {
  const { api } = useAuth();
  const [current, setCurrent] = useState(organization);
  const [busy, setBusy] = useState<MarkKind | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = async (kind: MarkKind, action: () => Promise<Organization>, fallback: string) => {
    setBusy(kind);
    setError(null);
    try {
      setCurrent(await action());
    } catch (err) {
      setError(errorText(err, fallback));
    } finally {
      setBusy(null);
    }
  };

  return (
    <>
      {error ? (
        <div className="section">
          <Banner tone="error" title={error} />
        </div>
      ) : null}
      <CellList
        mode="island"
        filled
        header={<CellHeader>Подпись и печать в документах</CellHeader>}
      >
        {KINDS.map(({ kind, title, has }) =>
          has(current) ? (
            <MarkRow
              key={kind}
              organizationId={current.id}
              kind={kind}
              title={title}
              version={current.updated_at}
              busy={busy !== null}
              onRemove={() =>
                void run(
                  kind,
                  () => api.deleteOrganizationMark(current.id, kind),
                  'Не удалось убрать картинку',
                )
              }
            />
          ) : (
            <FilePick
              key={kind}
              title={`Загрузить: ${title.toLowerCase()}`}
              subtitle="Фото на белом листе — фон станет прозрачным"
              icon={<IconCamera />}
              accept={PICTURES}
              busy={busy === kind}
              busyTitle="Загружаем…"
              onPick={(file) =>
                void run(
                  kind,
                  () => api.setOrganizationMark(current.id, kind, file),
                  'Не удалось загрузить картинку',
                )
              }
            />
          ),
        )}
      </CellList>
    </>
  );
}

interface MarkRowProps {
  organizationId: number;
  kind: MarkKind;
  title: string;
  version: string;
  busy: boolean;
  onRemove: () => void;
}

function MarkRow({ organizationId, kind, title, version, busy, onRemove }: MarkRowProps) {
  const { api } = useAuth();
  const [url, setUrl] = useState<string | null>(null);

  // Картинка приходит с Bearer, поэтому показывается через object URL; новая
  // редакция организации (version) — новая картинка.
  useEffect(() => {
    let created: string | null = null;
    let cancelled = false;
    api
      .organizationMark(organizationId, kind)
      .then((blob) => {
        if (cancelled) return;
        created = URL.createObjectURL(blob);
        setUrl(created);
      })
      .catch(() => setUrl(null));
    return () => {
      cancelled = true;
      if (created) URL.revokeObjectURL(created);
    };
  }, [api, organizationId, kind, version]);

  return (
    <>
      <CellSimple
        title={title}
        subtitle="Встаёт в строку подписи"
        after={url ? <img className="mark-preview" src={url} alt={title} /> : null}
      />
      <CellAction before={<IconTrash />} mode="destructive" disabled={busy} onClick={onRemove}>
        Убрать: {title.toLowerCase()}
      </CellAction>
    </>
  );
}
