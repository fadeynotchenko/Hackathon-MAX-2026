// Свой шаблон: единственный вход из каталога. Здесь выбирают — загрузить свой
// файл (готовый документ или фирменный бланк) или написать шаблон текстом.
// Файл разбирает сервер — места для данных находят метки {{…}} в файле или
// помощник, — а здесь человек проверяет их: убирает лишнее, отмечает
// пропущенное, выбирает тип и обязательность. Из DOCX документы потом
// собираются прямо в файле, с логотипом и оформлением; из PDF — на его листе.
import { Button, CellList, CellSimple, Typography } from '@maxhub/max-ui';
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import type { TemplateImport } from '@/api/client';
import { Banner } from '@/components/Banner';
import { DocPreview } from '@/components/DocPreview';
import { FieldInput } from '@/components/FieldInput';
import { FilePick } from '@/components/FilePick';
import { IconEdit, IconTemplates, IconUpload } from '@/components/icons';
import { Page, Section } from '@/components/Page';
import { useAuth } from '@/auth/context';
import { pluralize } from '@/lib/format';
import { errorText } from '@/lib/useAsync';
import { useBack } from '@/lib/useBack';
import { haptic, hapticResult } from '@/max/webapp';

import { DESCRIPTION_MAX, marker, TITLE_MAX } from './editor';
import { FieldPicker, FieldSettings, KindPicker } from './FieldControls';
import {
  addPlace,
  draftFromImport,
  labelText,
  markedInFile,
  placeFound,
  sampleProblems,
  sampleRequest,
  type SampleDraft,
  withoutField,
  withSampleField,
} from './sample';

const SAMPLE_TYPES =
  'application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,.docx,.pdf';

function useImport(onDone: (result: TemplateImport) => void) {
  const { api } = useAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pick = async (file: File) => {
    setBusy(true);
    setError(null);
    try {
      onDone(await api.importTemplate(file));
      hapticResult('success');
    } catch (err) {
      hapticResult('error');
      setError(errorText(err, 'Не удалось прочитать файл'));
    } finally {
      setBusy(false);
    }
  };
  return { busy, error, pick };
}

export function TemplateSamplePage() {
  const back = useBack('/create');
  const navigate = useNavigate();
  const [imported, setImported] = useState<{ result: TemplateImport; draft: SampleDraft } | null>(
    null,
  );
  const upload = useImport((result) => setImported({ result, draft: draftFromImport(result) }));

  if (imported) {
    return (
      <SampleEditor
        key={imported.result.file_id ?? imported.result.filename}
        initial={imported.draft}
        found={imported.result}
        templateId={null}
        onBack={back}
        onReplace={(result) => setImported({ result, draft: draftFromImport(result) })}
      />
    );
  }
  return (
    <Page title="Свой шаблон" subtitle="Заполняется так же, как стандартные" onBack={back}>
      {upload.error ? (
        <div className="section">
          <Banner tone="error" title={upload.error} />
        </div>
      ) : null}
      <CellList mode="island" filled>
        <FilePick
          icon={<IconUpload />}
          title="Загрузить свой файл"
          subtitle="DOCX или PDF — оформление сохранится"
          busy={upload.busy}
          busyTitle="Ищем места для данных…"
          accept={SAMPLE_TYPES}
          onPick={(file) => void upload.pick(file)}
        />
        <CellSimple
          title="Написать текстом"
          subtitle="Если файла нет"
          before={<IconEdit />}
          showChevron
          onClick={() => navigate('/templates/new')}
        />
      </CellList>
      <Typography.Text variant="description" color="tertiary" className="field__note">
        Подойдёт документ, который вы уже отправляли клиенту: клиента, суммы и даты найдём сами, а
        вы проверите. Место можно отметить и в файле: {marker('Название клиента')}.
      </Typography.Text>
    </Page>
  );
}

function foundText(
  found: TemplateImport,
  count: number,
): { tone: 'success' | 'info'; title: string; text: string } {
  if (count === 0) {
    return {
      tone: 'info',
      title: found.notice ?? 'Мест для данных не нашлось',
      text: 'Отметьте их ниже: скопируйте из файла текст, который меняется, и выберите поле.',
    };
  }
  const places = `${count} ${pluralize(count, 'место', 'места', 'мест')} для данных`;
  if (found.found_by === 'markers') {
    return {
      tone: 'success',
      title: `Нашли ${places}`,
      text: 'По меткам в файле. Проверьте типы полей.',
    };
  }
  if (found.found_by === 'rules') {
    return {
      tone: 'info',
      title: `Нашли ${places} по линейкам и реквизитам`,
      text: `${found.notice ? `${found.notice}. ` : ''}Лишнее уберите, пропущенное отметьте ниже.`,
    };
  }
  return {
    tone: 'success',
    title: `Помощник отметил ${places}`,
    text: 'Проверьте: лишнее уберите, пропущенное отметьте ниже.',
  };
}

interface SampleEditorProps {
  initial: SampleDraft;
  // Заголовок экрана нового шаблона: «Свой на основе стандартного».
  heading?: string | undefined;
  // null — новый шаблон.
  templateId: number | null;
  onBack: () => void;
  // Что нашёл разбор файла — для подсказки над списком; при правке нет.
  found?: TemplateImport;
  onReplace?: (result: TemplateImport) => void;
}

export function SampleEditor({
  initial,
  heading,
  templateId,
  onBack,
  found,
  onReplace,
}: SampleEditorProps) {
  const { api } = useAuth();
  const navigate = useNavigate();
  const [draft, setDraft] = useState(initial);
  const [fragment, setFragment] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const replace = useImport((result) => {
    if (onReplace) {
      onReplace(result);
    } else {
      // Правка шаблона: новый файл вместо прежнего, название и описание — свои.
      setDraft({ ...draftFromImport(result), title: draft.title, description: draft.description });
    }
  });
  const preview = useMemo(() => labelText(draft), [draft]);
  const text = fragment.trim();
  const fragmentMissing = Boolean(text) && !placeFound(draft.text, { text, before: '' });
  const isPdf = draft.filename.toLowerCase().endsWith('.pdf');
  const notice = found ? foundText(found, initial.fields.length) : null;

  const fail = (message: string) => {
    hapticResult('error');
    setError(message);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const save = async () => {
    const problems = sampleProblems(draft);
    if (problems.length > 0) {
      fail(problems.join('. '));
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const body = sampleRequest(draft);
      if (templateId !== null) {
        await api.updateTemplate(templateId, body);
        hapticResult('success');
        onBack();
      } else {
        const saved = await api.createTemplate(body);
        hapticResult('success');
        void navigate(`/create/${saved.id}`, { replace: true });
      }
    } catch (err) {
      fail(errorText(err, 'Не удалось сохранить шаблон'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Page
      title={templateId !== null ? 'Изменить шаблон' : (heading ?? 'Проверьте шаблон')}
      subtitle={draft.filename}
      onBack={onBack}
      footer={
        <Button size="large" stretched loading={saving} onClick={() => void save()}>
          Сохранить шаблон
        </Button>
      }
    >
      {error ? (
        <div className="section">
          <Banner tone="error" title="Шаблон не сохранён">
            {error}
          </Banner>
        </div>
      ) : null}
      {replace.error ? (
        <div className="section">
          <Banner tone="error" title={replace.error} />
        </div>
      ) : null}

      <CellList mode="island" filled>
        <CellSimple
          title={draft.filename || 'Файл-образец'}
          subtitle={
            isPdf ? 'PDF · лист сохранится как есть' : 'DOCX · логотип и оформление сохранятся'
          }
          innerClassNames={{ title: 'ellipsis' }}
          before={<IconTemplates />}
        />
        <FilePick
          icon={<IconUpload />}
          title="Выбрать другой файл"
          busy={replace.busy}
          busyTitle="Ищем места для данных…"
          accept={SAMPLE_TYPES}
          onPick={(file) => void replace.pick(file)}
        />
      </CellList>

      {notice ? (
        <div className="section">
          <Banner tone={notice.tone} title={notice.title}>
            {notice.text}
          </Banner>
        </div>
      ) : null}

      <Section>
        <div className="fields">
          <KindPicker value={draft.kind} onChange={(kind) => setDraft({ ...draft, kind })} />
          <FieldInput
            label="Название шаблона"
            type="text"
            value={draft.title}
            maxLength={TITLE_MAX}
            hint="Так шаблон будет называться в каталоге и в чате с ботом"
            onChange={(value) => setDraft({ ...draft, title: value })}
          />
          <FieldInput
            label="Описание"
            type="text"
            required={false}
            value={draft.description}
            maxLength={DESCRIPTION_MAX}
            onChange={(value) => setDraft({ ...draft, description: value })}
          />
        </div>
      </Section>

      <Section
        title="Места для данных"
        after={
          draft.fields.length > 0 ? (
            <Typography.Text variant="description" color="tertiary">
              {draft.fields.length} {pluralize(draft.fields.length, 'поле', 'поля', 'полей')}
            </Typography.Text>
          ) : null
        }
      >
        {draft.fields.length === 0 ? (
          <Typography.Text variant="description" color="tertiary" className="field__note">
            Пока ни одного — отметьте места ниже.
          </Typography.Text>
        ) : (
          <div className="fields">
            {draft.fields.map((field) => (
              <FieldSettings
                key={field.key}
                field={field}
                onChange={(next) => setDraft(withSampleField(draft, next))}
                {...(field.places.length === 0 && markedInFile(draft.text, field.key)
                  ? {}
                  : {
                      onRemove: () => {
                        haptic('light');
                        setDraft(withoutField(draft, field.key));
                      },
                    })}
              >
                <Typography.Text
                  variant="description"
                  color="secondary"
                  className="template-field__place clamp-2"
                >
                  {field.places.length === 0 && markedInFile(draft.text, field.key)
                    ? 'В бланке — своя метка поля'
                    : `В файле: ${field.places.map((place) => `«${place.text}»`).join(', ')}`}
                </Typography.Text>
              </FieldSettings>
            ))}
          </div>
        )}
      </Section>

      <Section title="Отметить место">
        <div className="fields">
          <FieldInput
            label="Текст из файла"
            type="text"
            value={fragment}
            error={fragmentMissing ? 'Такого текста в файле нет — скопируйте его точно' : null}
            hint="То, что меняется от документа к документу: имя клиента, сумма, дата"
            onChange={setFragment}
          />
          {text && !fragmentMissing ? (
            <FieldPicker
              customAction="Своё поле с этим названием"
              onInsert={(label) => {
                setDraft(addPlace(draft, label, { text, before: '' }));
                setFragment('');
                haptic('light');
              }}
            />
          ) : null}
        </div>
      </Section>

      <Section title="Текст с полями">
        <DocPreview text={preview} marks={false} />
      </Section>
    </Page>
  );
}
