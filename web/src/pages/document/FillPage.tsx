// Шаг 1 из 3 — данные. Форма по разделам шаблона: у каждого значения виден
// источник, ошибка проверки — под полем. «Проверить документ» сохраняет и
// пускает дальше, только когда ошибок и пустых обязательных полей нет:
// исправление идёт здесь же, без отдельных экранов «ошибка» и «исправлено».
// Пустые необязательные поля свёрнуты в «Ещё N полей»: на экране сначала то,
// без чего документ не собрать.
//
// Сверху — три способа заполнить форму за человека, как в чате с ботом: с фото,
// голосом, текстом. У каждого свой экран (fillMethods.ts); несохранённые правки
// уходят на сервер до перехода, а по возвращении форма перечитывает документ и
// показывает плашку, оставленную экраном способа. Администратору под ними видна
// кнопка тестовых данных: на время испытаний форму не набирают руками.
import { Button, CellHeader, CellList, CellSimple } from '@maxhub/max-ui';
import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import type { DocumentView } from '@/api/client';
import { Banner } from '@/components/Banner';
import { FieldInput } from '@/components/FieldInput';
import { IconCamera, IconMic, IconPlus, IconText } from '@/components/icons';
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
  documentTitle,
  draftFromDocument,
  fieldErrors,
  mergeAfterSave,
  sourceOf,
  type Draft,
} from './fields';
import {
  dropNotice,
  fillMethodPath,
  peekNotice,
  type FillMethod,
  type FillNotice,
} from './fillMethods';
import { mockValues } from './mock';

const FILL_METHODS: Array<{ method: FillMethod; label: string; Icon: typeof IconCamera }> = [
  { method: 'photo', label: 'С фото', Icon: IconCamera },
  { method: 'voice', label: 'Голосом', Icon: IconMic },
  { method: 'text', label: 'Текстом', Icon: IconText },
];

function filledKeys(draft: Draft): string[] {
  return Object.keys(draft).filter((key) => draft[key]?.trim());
}

export function FillPage() {
  const { api } = useAuth();
  const documentId = Number(useParams().documentId);
  const back = useBack(`/documents/${documentId}`);
  const loaded = useAsync(() => api.document(documentId), [api, documentId]);

  if (!loaded.data) {
    return (
      <Page title="Документ" onBack={back}>
        {loaded.error ? <ErrorState message={loaded.error} onRetry={loaded.reload} /> : <Loading />}
      </Page>
    );
  }
  return <FillForm key={loaded.data.id} loaded={loaded.data} onBack={back} />;
}

function FillForm({ loaded, onBack }: { loaded: DocumentView; onBack: () => void }) {
  const { api, user } = useAuth();
  const navigate = useNavigate();
  const [doc, setDoc] = useState(loaded);
  const [draft, setDraft] = useState<Draft>(() => draftFromDocument(loaded));
  const [initial, setInitial] = useState<Draft>(() => draftFromDocument(loaded));
  const [checked, setChecked] = useState(false);
  const [saving, setSaving] = useState(false);
  // Сохраняем правки перед переходом к способу заполнения.
  const [leaving, setLeaving] = useState(false);
  const [testing, setTesting] = useState(false);
  // Плашка, оставленная экраном способа заполнения, показывается один раз.
  const [notice, setNotice] = useState<FillNotice | null>(() => peekNotice(loaded.id));
  const [sellerOpen, setSellerOpen] = useState(false);
  // Необязательное поле, раз показанное (есть значение или раскрыли группу),
  // не прячется обратно, даже если его стереть.
  const [revealed, setRevealed] = useState<Set<string>>(
    () => new Set(filledKeys(draftFromDocument(loaded))),
  );
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  useEffect(() => {
    dropNotice(loaded.id);
  }, [loaded.id]);

  // Отклонённое значение становится «исходным»: любая его правка, даже
  // стирание, уйдёт на повторную проверку, а без правки ошибка останется.
  const apply = (next: DocumentView, current: Draft) => {
    const merged = mergeAfterSave(next, current);
    setDoc(next);
    setDraft(merged);
    setInitial(merged);
    setRevealed((prev) => new Set([...prev, ...filledKeys(merged)]));
  };

  // Несохранённые правки уходят на сервер до перехода к способу заполнения и перед проверкой.
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

  // Отклонённую правку сервер не хранит: уйди форма к способу заполнения, она
  // пропала бы молча. Поэтому с ошибкой в только что изменённом поле форма
  // остаётся на месте, как при проверке.
  const openMethod = async (method: FillMethod) => {
    setLeaving(true);
    setNotice(null);
    const changed = changedValues(draft, initial);
    try {
      const next = await save();
      const lost = new Set(next.errors.filter((e) => e.key in changed).map((e) => e.key)).size;
      if (lost > 0) {
        hapticResult('error');
        setNotice({
          tone: 'error',
          title: `Исправьте ${lost} ${pluralize(lost, 'поле', 'поля', 'полей')}`,
        });
        setLeaving(false);
        return;
      }
      void navigate(fillMethodPath(doc.id, method));
    } catch (err) {
      setNotice({ tone: 'error', title: errorText(err, 'Не удалось сохранить') });
      setLeaving(false);
    }
  };

  // Тестовые данные заменяют все поля, поэтому раскрывается вся форма: видно,
  // что подставилось, в том числе в свёрнутых группах и реквизитах продавца.
  const fillWithMock = async () => {
    setTesting(true);
    setNotice(null);
    try {
      const values = mockValues(doc.template.fields);
      const next = await api.setFields(doc.id, values);
      apply(next, { ...draft, ...values });
      setRevealed(new Set(next.template.fields.map((field) => field.key)));
      setExpanded(new Set(next.template.fields.map((field) => field.group)));
      setSellerOpen(true);
      hapticResult('success');
      setNotice({ tone: 'success', title: 'Тестовые данные подставлены' });
    } catch (err) {
      setNotice({ tone: 'error', title: errorText(err, 'Не удалось подставить данные') });
    } finally {
      setTesting(false);
    }
  };

  const busy = saving || leaving || testing;
  const errors = fieldErrors(doc, checked);
  const groups = groupFields(doc.template.fields);
  const sellerFields = doc.template.fields.filter((field) => field.group === 'Продавец');
  const sellerFromProfile =
    sellerFields.length > 0 &&
    sellerFields.every((field) => !field.required || doc.values[field.key]?.source === 'profile') &&
    !sellerFields.some((field) => errors[field.key]);

  return (
    <Page
      title={documentTitle(doc)}
      onBack={onBack}
      footer={
        <Button size="large" stretched loading={saving} onClick={() => void check()}>
          Проверить документ
        </Button>
      }
    >
      <Steps current={1} />
      {notice ? (
        <div className="section">
          <Banner tone={notice.tone} title={notice.title}>
            {notice.text}
          </Banner>
        </div>
      ) : null}

      <Section title="Заполнить с помощником">
        <div className="fill-methods">
          {FILL_METHODS.map(({ method, label, Icon }) => (
            <button
              key={method}
              type="button"
              className="fill-method"
              disabled={busy}
              onClick={() => void openMethod(method)}
            >
              <Icon className="fill-method__icon" size={28} />
              <span className="fill-method__label">{label}</span>
            </button>
          ))}
        </div>
        {user?.is_admin ? (
          <Button
            className="fill-test"
            variant="secondary"
            size="medium"
            stretched
            loading={testing}
            disabled={busy && !testing}
            onClick={() => void fillWithMock()}
          >
            Тест — мок данных
          </Button>
        ) : null}
      </Section>

      {groups.map(([group, fields]) => {
        const title = GROUP_TITLE[group] ?? group;
        if (group === 'Продавец' && sellerFromProfile && !sellerOpen) {
          return (
            <CellList key={group} mode="island" filled header={<CellHeader>{title}</CellHeader>}>
              <CellSimple
                title={doc.values['seller_name']?.value ?? 'Реквизиты организации'}
                subtitle="Из профиля"
                showChevron
                onClick={() => setSellerOpen(true)}
              />
            </CellList>
          );
        }
        const shown = fields.filter(
          (field) =>
            field.required ||
            expanded.has(group) ||
            revealed.has(field.key) ||
            Boolean(errors[field.key]),
        );
        const hidden = fields.length - shown.length;
        return (
          <Section key={group} title={title}>
            <div className="fields">
              {shown.map((field) => (
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
              {hidden > 0 ? (
                <button
                  type="button"
                  className="link-button"
                  onClick={() => setExpanded((prev) => new Set(prev).add(group))}
                >
                  <IconPlus size={20} />
                  Ещё {hidden} {pluralize(hidden, 'поле', 'поля', 'полей')}
                </button>
              ) : null}
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
