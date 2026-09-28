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
//
// Стороны выбираются здесь же: в разделе клиента — карточка из клиентов, в
// «Вашей организации» — от какой своей организации документ. Выбор — свой экран
// (parties.ts), путь к нему тот же, что к способу заполнения.
//
// Действия формы (проверка, переход, тестовые данные) идут по одному: пока одно
// ждёт сервер, остальные кнопки выключены, а ушла форма «Назад» — ответ уже
// никуда её не ведёт.
import { Button, CellHeader, CellList, CellSimple } from '@maxhub/max-ui';
import { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import type { DocumentView, Organization } from '@/api/client';
import { Banner } from '@/components/Banner';
import { FieldInput } from '@/components/FieldInput';
import {
  IconBuilding,
  IconCamera,
  IconEdit,
  IconMic,
  IconPlus,
  IconText,
  IconUsers,
} from '@/components/icons';
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
  rejectedEdits,
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
import { partyPickPath } from './parties';

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
  // Свои организации — для ячейки «От кого»: как зовут текущую и есть ли из чего
  // выбирать. Грузятся вместе с документом; ошибка списка форму не держит.
  const organizations = useAsync(() => api.organizations(), [api]);

  if (!loaded.data || organizations.loading) {
    return (
      <Page title="Документ" onBack={back}>
        {loaded.error ? <ErrorState message={loaded.error} onRetry={loaded.reload} /> : <Loading />}
      </Page>
    );
  }
  return (
    <FillForm
      key={loaded.data.id}
      loaded={loaded.data}
      organizations={organizations.data}
      onBack={back}
    />
  );
}

interface FillFormProps {
  loaded: DocumentView;
  // null — список не загрузился: «От кого» берёт название из самого документа.
  organizations: Organization[] | null;
  onBack: () => void;
}

function FillForm({ loaded, organizations, onBack }: FillFormProps) {
  const { api, user } = useAuth();
  const navigate = useNavigate();
  const [doc, setDoc] = useState(loaded);
  const [draft, setDraft] = useState<Draft>(() => draftFromDocument(loaded));
  const [initial, setInitial] = useState<Draft>(() => draftFromDocument(loaded));
  const [checked, setChecked] = useState(false);
  const [saving, setSaving] = useState(false);
  // Сохраняем правки перед переходом к способу заполнения или выбору стороны.
  const [leaving, setLeaving] = useState(false);
  const [testing, setTesting] = useState(false);
  // Плашка, оставленная экраном способа или выбора стороны, показывается один раз.
  const [notice, setNotice] = useState<FillNotice | null>(() => peekNotice(loaded.id));
  const [sellerOpen, setSellerOpen] = useState(false);
  // Необязательное поле, раз показанное (есть значение или раскрыли группу),
  // не прячется обратно, даже если его стереть.
  const [revealed, setRevealed] = useState<Set<string>>(
    () => new Set(filledKeys(draftFromDocument(loaded))),
  );
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  // Второй тап может прийти раньше перерисовки с busy.
  const running = useRef(false);
  const mounted = useRef(false);

  useEffect(() => {
    dropNotice(loaded.id);
  }, [loaded.id]);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  // Отклонённое значение становится «исходным»: любая его правка, даже
  // стирание, уйдёт на повторную проверку, а без правки ошибка останется.
  const apply = (next: DocumentView, current: Draft) => {
    const merged = mergeAfterSave(next, current);
    setDoc(next);
    setDraft(merged);
    setInitial(merged);
    setRevealed((prev) => new Set([...prev, ...filledKeys(merged)]));
  };

  // Несохранённые правки уходят на сервер до перехода с формы и перед проверкой.
  // Отклонённые — с ними каждый раз, пока стоят в поле (rejectedEdits в fields.ts).
  const save = async (): Promise<DocumentView> => {
    const changed = { ...rejectedEdits(doc, draft), ...changedValues(draft, initial) };
    if (Object.keys(changed).length === 0) return doc;
    const next = await api.setFields(doc.id, changed);
    apply(next, draft);
    return next;
  };

  const check = async () => {
    if (running.current) return;
    running.current = true;
    setSaving(true);
    setNotice(null);
    try {
      const next = await save();
      if (!mounted.current) return;
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
      if (!mounted.current) return;
      setNotice({ tone: 'error', title: errorText(err, 'Не удалось сохранить') });
    } finally {
      running.current = false;
      setSaving(false);
    }
  };

  // Уйти с формы — к способу заполнения или к выбору стороны. Отклонённую правку
  // сервер не хранит: уйди форма с ней, она пропала бы молча. Поэтому, пока в
  // поле стоит отклонённое значение, форма остаётся на месте, как при проверке.
  const leaveTo = async (to: string, state?: { returnTo: string }) => {
    if (running.current) return;
    running.current = true;
    setLeaving(true);
    setNotice(null);
    try {
      const next = await save();
      if (!mounted.current) return;
      const lost = Object.keys(rejectedEdits(next, draft)).length;
      if (lost === 0) {
        // leaving не снимается: экран уходит.
        void navigate(to, state ? { state } : undefined);
        return;
      }
      hapticResult('error');
      setNotice({
        tone: 'error',
        title: `Исправьте ${lost} ${pluralize(lost, 'поле', 'поля', 'полей')}`,
      });
    } catch (err) {
      if (!mounted.current) return;
      setNotice({ tone: 'error', title: errorText(err, 'Не удалось сохранить') });
    }
    running.current = false;
    setLeaving(false);
  };

  const openMethod = (method: FillMethod) => void leaveTo(fillMethodPath(doc.id, method));
  const pickClient = () => void leaveTo(partyPickPath(doc.id, 'client'));
  const pickSeller = () => void leaveTo(partyPickPath(doc.id, 'seller'));
  // Своих организаций нет — сразу в форму новой: выбирать всё равно не из чего,
  // а сохранённую выбор «От кого» подставит в документ сам.
  const addSeller = () =>
    void leaveTo('/profile/organizations/new', { returnTo: partyPickPath(doc.id, 'seller') });

  // Тестовые данные заменяют все поля, поэтому раскрывается вся форма: видно,
  // что подставилось, в том числе в свёрнутых группах и реквизитах продавца.
  const fillWithMock = async () => {
    if (running.current) return;
    running.current = true;
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
      running.current = false;
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

  // Карточка клиента: имя — из документа (из карточки оно туда и пришло).
  const clientPick = doc.counterparty_id ? (
    <CellSimple
      surface="island"
      title={doc.values['client_name']?.value || 'Карточка клиента'}
      subtitle="Из карточки клиентов"
      innerClassNames={{ title: 'clamp-2' }}
      before={<IconUsers />}
      showChevron
      disabled={busy}
      onClick={pickClient}
    />
  ) : (
    <CellSimple
      surface="island"
      title="Выбрать из клиентов"
      before={
        <span className="themed-icon">
          <IconUsers />
        </span>
      }
      showChevron
      disabled={busy}
      onClick={pickClient}
    />
  );

  const organizationName =
    organizations?.find((item) => item.id === doc.organization_id)?.name ??
    doc.values['seller_name']?.value;
  // Своя ячейка-остров над полями продавца; в свёрнутом виде — строка списка.
  const sellerPick = (surface: 'island' | 'default') =>
    organizations?.length === 0 ? (
      <CellSimple
        surface={surface}
        title="Добавить свою организацию"
        subtitle="Реквизиты подставятся в документ"
        before={
          <span className="themed-icon">
            <IconPlus />
          </span>
        }
        showChevron
        disabled={busy}
        onClick={addSeller}
      />
    ) : (
      <CellSimple
        surface={surface}
        overline="От кого"
        title={organizationName || 'Выбрать организацию'}
        innerClassNames={{ title: 'clamp-2' }}
        before={<IconBuilding />}
        showChevron
        disabled={busy}
        onClick={pickSeller}
      />
    );

  return (
    <Page
      title={documentTitle(doc)}
      onBack={onBack}
      footer={
        <Button
          size="large"
          stretched
          loading={saving}
          disabled={busy && !saving}
          onClick={() => void check()}
        >
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
              onClick={() => openMethod(method)}
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
              {sellerPick('default')}
              <CellSimple
                title="Реквизиты"
                subtitle="Из профиля"
                before={<IconEdit />}
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
            {group === 'Клиент' ? clientPick : null}
            {group === 'Продавец' ? sellerPick('island') : null}
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
