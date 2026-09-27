// Форма реквизитов организации: своей или клиента. Можно заполнить с фото
// карточки предприятия — распознанное подставляется в поля и помечается,
// а сохраняет человек, проверив значения. Пример значения — плейсхолдером
// в пустом поле, а не строкой под ним.
import { CellList } from '@maxhub/max-ui';
import { useState } from 'react';

import { ApiError } from '@/api/client';
import { Banner } from '@/components/Banner';
import { FieldInput } from '@/components/FieldInput';
import { FilePick } from '@/components/FilePick';
import { IconCamera } from '@/components/icons';
import { Section } from '@/components/Page';
import { useAuth } from '@/auth/context';
import { pluralize } from '@/lib/format';
import { errorText } from '@/lib/useAsync';

import { REQUISITE_GROUPS, type Requisites } from './requisites';

export interface RequisitesFormProps {
  values: Requisites;
  onChange: (values: Requisites) => void;
  errors: Record<string, string>;
}

export function RequisitesForm({ values, onChange, errors }: RequisitesFormProps) {
  const { api } = useAuth();
  const [recognized, setRecognized] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{
    tone: 'success' | 'error';
    title: string;
    text?: string;
  } | null>(null);

  const recognize = async (file: File) => {
    setBusy(true);
    setNotice(null);
    try {
      const result = await api.recognizeRequisites(file);
      const found = Object.fromEntries(
        Object.entries(result.values).map(([key, value]) => [key, value.value]),
      );
      const keys = Object.keys(found);
      onChange({ ...values, ...found });
      setRecognized(new Set(keys));
      const skipped = result.errors.map((error) => `Не подставлено: ${error.message}`).join(' ');
      setNotice(
        keys.length > 0
          ? {
              tone: 'success',
              title: `Заполнено ${keys.length} ${pluralize(keys.length, 'поле', 'поля', 'полей')} — сверьте с фото`,
              ...(skipped ? { text: skipped } : {}),
            }
          : { tone: 'error', title: 'Реквизитов на файле не нашлось' },
      );
    } catch (err) {
      setNotice({
        tone: 'error',
        title:
          err instanceof ApiError && err.status === 503
            ? 'Распознавание сейчас недоступно — заполните вручную'
            : errorText(err, 'Не удалось распознать файл'),
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <CellList mode="island" filled>
        <FilePick
          icon={<IconCamera />}
          busy={busy}
          title="Заполнить с фото"
          onPick={(file) => void recognize(file)}
        />
      </CellList>
      {notice ? (
        <div className="section">
          <Banner tone={notice.tone} title={notice.title}>
            {notice.text}
          </Banner>
        </div>
      ) : null}
      {REQUISITE_GROUPS.map((group) => (
        <Section key={group.title} title={group.title}>
          <div className="fields">
            {group.fields.map((field) => (
              <FieldInput
                key={field.key}
                label={field.label}
                type={field.type}
                placeholder={field.example}
                value={values[field.key] ?? ''}
                maxLength={field.maxLength}
                error={errors[field.key]}
                source={recognized.has(field.key) ? { label: 'С фото', draft: true } : null}
                onChange={(value) => {
                  setRecognized((prev) => {
                    const next = new Set(prev);
                    next.delete(field.key);
                    return next;
                  });
                  onChange({ ...values, [field.key]: value });
                }}
              />
            ))}
          </div>
        </Section>
      ))}
    </>
  );
}
