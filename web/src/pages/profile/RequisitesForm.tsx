// Форма реквизитов организации: своей или клиента. Можно заполнить с фото
// карточки предприятия — распознанное подставляется в поля и помечается,
// а сохраняет человек, проверив значения. Пример значения — плейсхолдером
// в пустом поле, а не строкой под ним.
//
// Название и ИНН ищут организацию в реестре и заполняют юрданные целиком,
// банк и БИК — банк с корр. счётом, адрес — сам себя (lib/suggest.ts).
import { CellList, CellSimple } from '@maxhub/max-ui';
import { useState } from 'react';

import { ApiError, type FieldType, type RequisiteSuggestion } from '@/api/client';
import { Banner } from '@/components/Banner';
import { FieldInput } from '@/components/FieldInput';
import { FilePick } from '@/components/FilePick';
import { IconCamera, IconSparkle } from '@/components/icons';
import { Section } from '@/components/Page';
import { useAuth } from '@/auth/context';
import { pluralize } from '@/lib/format';
import {
  REGISTRY_SOURCE,
  SUGGEST_TITLE,
  suggestTarget,
  suggestUnavailable,
  suggestionValues,
} from '@/lib/suggest';
import { errorText } from '@/lib/useAsync';

import { REQUISITE_GROUPS, type Requisites } from './requisites';

export interface RequisitesFormProps {
  values: Requisites;
  onChange: (values: Requisites) => void;
  errors: Record<string, string>;
  // Чьи реквизиты: своей организации или клиента — для тестового набора на стенде.
  side: 'seller' | 'client';
}

export function RequisitesForm({ values, onChange, errors, side }: RequisitesFormProps) {
  const { api, mode } = useAuth();
  // Ключ → откуда значение: «С фото» ждёт сверки, «Из реестра» — нет.
  const [filledFrom, setFilledFrom] = useState<Map<string, 'photo' | 'registry'>>(new Map());
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
      setFilledFrom(new Map(keys.map((key) => [key, 'photo'])));
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

  // Стенд вне MAX: сходящиеся ИНН, БИК и счета руками не придумать.
  const fillDemo = async () => {
    setNotice(null);
    try {
      const demo = await api.devRequisites();
      onChange({ ...values, ...demo[side] });
      setFilledFrom(new Map());
      setNotice({
        tone: 'success',
        title: 'Подставлены тестовые реквизиты — они проходят проверку',
      });
    } catch (err) {
      setNotice({ tone: 'error', title: errorText(err, 'Тестовые реквизиты недоступны') });
    }
  };

  const suggestFor = (key: string, type: FieldType) => {
    const target = suggestTarget(key, type, ['']);
    if (!target) return undefined;
    return {
      title: SUGGEST_TITLE[target.kind],
      fetch: (query: string) => api.suggest(target.kind, query),
      onPick: (suggestion: RequisiteSuggestion) => {
        const found = suggestionValues(target, key, suggestion, null);
        onChange({ ...values, ...found });
        setFilledFrom((prev) => {
          const next = new Map(prev);
          for (const filled of Object.keys(found)) next.set(filled, 'registry');
          return next;
        });
      },
    };
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
        {mode === 'dev' ? (
          <CellSimple
            title="Тестовые реквизиты"
            subtitle="Только на стенде: ИНН, БИК и счета сходятся"
            before={<IconSparkle />}
            showChevron
            onClick={() => void fillDemo()}
          />
        ) : null}
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
                placeholder={
                  (suggestUnavailable() ? undefined : field.suggestHint) ?? field.example
                }
                value={values[field.key] ?? ''}
                maxLength={field.maxLength}
                error={errors[field.key]}
                source={FILLED_FROM[filledFrom.get(field.key) ?? 'none']}
                suggest={suggestFor(field.key, field.type)}
                onChange={(value) => {
                  setFilledFrom((prev) => {
                    const next = new Map(prev);
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

const FILLED_FROM = {
  photo: { label: 'С фото', draft: true },
  registry: REGISTRY_SOURCE,
  none: null,
} as const;
