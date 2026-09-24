// Шаг 1 из 3 — данные. Форма по разделам шаблона: у каждого значения виден
// источник, ошибка проверки — под полем. «Проверить документ» сохраняет и
// пускает дальше, только когда ошибок и пустых обязательных полей нет:
// исправление идёт здесь же, без отдельных экранов «ошибка» и «исправлено».
import { Button, CellHeader, CellList, CellSimple } from '@maxhub/max-ui';
import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import type { DocumentView } from '@/api/client';
import { Banner } from '@/components/Banner';
import { FieldInput } from '@/components/FieldInput';
import { FilePick } from '@/components/FilePick';
import { IconCamera } from '@/components/icons';
import { Page, Section } from '@/components/Page';
import { ErrorState, Loading } from '@/components/StateViews';
import { Steps } from '@/components/Steps';
import { useAuth } from '@/auth/context';
import { GROUP_TITLE, groupFields, pluralize } from '@/lib/format';
import { errorText, useAsync } from '@/lib/useAsync';
import { useBack } from '@/lib/useBack';
import { hapticResult } from '@/max/webapp';

import {
  changedValues,
  documentCaption,
  draftFromDocument,
  fieldErrors,
  mergeAfterSave,
  sourceOf,
  type Draft,
} from './fields';

type Notice = { tone: 'success' | 'error' | 'info'; title: string; text?: string } | null;

export function FillPage() {
  const { api } = useAuth();
  const documentId = Number(useParams().documentId);
  const back = useBack(`/documents/${documentId}`);
  const loaded = useAsync(() => api.document(documentId), [api, documentId]);

  if (!loaded.data) {
    return (
      <Page title="Данные документа" onBack={back}>
        {loaded.error ? <ErrorState message={loaded.error} onRetry={loaded.reload} /> : <Loading />}
      </Page>
    );
  }
  return <FillForm key={loaded.data.id} loaded={loaded.data} onBack={back} />;
}

function FillForm({ loaded, onBack }: { loaded: DocumentView; onBack: () => void }) {
  const { api } = useAuth();
  const navigate = useNavigate();
  const [doc, setDoc] = useState(loaded);
  const [draft, setDraft] = useState<Draft>(() => draftFromDocument(loaded));
  const [initial, setInitial] = useState<Draft>(() => draftFromDocument(loaded));
  const [checked, setChecked] = useState(false);
  const [saving, setSaving] = useState(false);
  const [recognizing, setRecognizing] = useState(false);
  const [notice, setNotice] = useState<Notice>(null);
  const [sellerOpen, setSellerOpen] = useState(false);

  // Отклонённое значение становится «исходным»: любая его правка, даже
  // стирание, уйдёт на повторную проверку, а без правки ошибка останется.
  const apply = (next: DocumentView, current: Draft) => {
    const merged = mergeAfterSave(next, current);
    setDoc(next);
    setDraft(merged);
    setInitial(merged);
  };

  // Несохранённые правки уходят на сервер до распознавания и перед проверкой.
  const save = async (): Promise<DocumentView> => {
    const changed = changedValues(draft, initial);
    if (Object.keys(changed).length === 0) return doc;
    const next = await api.setFields(doc.id, changed);
    apply(next, draft);
    return next;
  };

  const check = async () => {
    setSaving(true);
    setNotice(null);
    try {
      const next = await save();
      setChecked(true);
      if (next.errors.length > 0 || next.missing.length > 0) {
        hapticResult('error');
        const count = new Set([...next.errors.map((e) => e.key), ...next.missing]).size;
        setNotice({
          tone: 'error',
          title: `Исправьте ${count} ${pluralize(count, 'поле', 'поля', 'полей')}`,
          text: 'Они выделены ниже. Остальные данные сохранены.',
        });
        if (next.template.fields.some((f) => f.group === 'Продавец' && isBad(next, f.key))) {
          setSellerOpen(true);
        }
        window.scrollTo({ top: 0, behavior: 'smooth' });
        return;
      }
      void navigate(`/documents/${doc.id}/review`);
    } catch (err) {
      setNotice({ tone: 'error', title: errorText(err, 'Не удалось сохранить') });
    } finally {
      setSaving(false);
    }
  };

  const recognize = async (file: File) => {
    setRecognizing(true);
    setNotice(null);
    try {
      await save();
      const result = await api.recognizeIntoDocument(doc.id, file);
      apply(result.document, draftFromDocument(result.document));
      const filled = result.filled.length;
      setNotice(
        filled > 0
          ? {
              tone: 'success',
              title: `С файла заполнено ${filled} ${pluralize(filled, 'поле', 'поля', 'полей')}`,
              text: 'Значения отмечены «С фото · проверьте» — сверьте их с оригиналом.',
            }
          : {
              tone: 'info',
              title: 'На файле не нашлось данных для этого документа',
              text: result.reply,
            },
      );
    } catch (err) {
      setNotice({ tone: 'error', title: errorText(err, 'Не удалось распознать файл') });
    } finally {
      setRecognizing(false);
    }
  };

  const errors = fieldErrors(doc, checked);
  const groups = groupFields(doc.template.fields);
  const sellerFields = doc.template.fields.filter((field) => field.group === 'Продавец');
  const sellerFromProfile =
    sellerFields.length > 0 &&
    sellerFields.every((field) => !field.required || doc.values[field.key]?.source === 'profile') &&
    !sellerFields.some((field) => errors[field.key]);

  return (
    <Page
      title="Заполните данные"
      subtitle={documentCaption(doc)}
      onBack={onBack}
      footer={
        <Button size="large" stretched loading={saving} onClick={() => void check()}>
          Проверить документ
        </Button>
      }
    >
      <div className="section">
        <Steps current={1} />
      </div>
      {notice ? (
        <div className="section">
          <Banner tone={notice.tone} title={notice.title}>
            {notice.text}
          </Banner>
        </div>
      ) : null}

      <CellList mode="island" filled>
        <FilePick
          icon={<IconCamera />}
          busy={recognizing}
          title="Заполнить с фото или скана"
          subtitle="Карточка предприятия, счёт или договор"
          onPick={(file) => void recognize(file)}
        />
      </CellList>

      {groups.map(([group, fields]) => {
        const title = GROUP_TITLE[group] ?? group;
        if (group === 'Продавец' && sellerFromProfile && !sellerOpen) {
          return (
            <CellList key={group} mode="island" filled header={<CellHeader>{title}</CellHeader>}>
              <CellSimple
                title={doc.values['seller_name']?.value ?? 'Реквизиты организации'}
                subtitle="Из «Моих организаций» · нажмите, чтобы изменить"
                showChevron
                onClick={() => setSellerOpen(true)}
              />
            </CellList>
          );
        }
        return (
          <Section key={group} title={title}>
            <div className="fields">
              {fields.map((field) => (
                <div key={field.key} data-field={field.key}>
                  <FieldInput
                    label={field.label}
                    type={field.type}
                    required={field.required}
                    hint={field.hint || undefined}
                    maxLength={field.max_length}
                    value={draft[field.key] ?? ''}
                    error={errors[field.key]}
                    // Отклонённое значение в поле — то, что ввёл человек, а сервер
                    // хранит прежнее: метка «Из карточки» рядом с ним соврала бы.
                    source={
                      !errors[field.key] && draft[field.key] === initial[field.key]
                        ? sourceOf(doc, field)
                        : null
                    }
                    onChange={(value) => setDraft((prev) => ({ ...prev, [field.key]: value }))}
                  />
                </div>
              ))}
            </div>
          </Section>
        );
      })}
    </Page>
  );
}

function isBad(doc: DocumentView, key: string): boolean {
  return doc.missing.includes(key) || doc.errors.some((error) => error.key === key);
}
