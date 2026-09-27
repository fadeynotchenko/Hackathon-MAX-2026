// Свой шаблон: название, текст и поля. Поле ставится кнопкой «Вставить поле»
// или пишется прямо в тексте названием в двойных фигурных скобках; список
// полей и лист предпросмотра собираются по тексту на лету. Реквизиты сторон
// берутся из каталога — тогда в документе они подставятся сами.
//
// Экран открывается пустым (/templates/new), копией стандартного шаблона
// (/templates/new?from=1), текстом PDF-образца (/templates/new с черновиком в
// state) или правкой своего (/templates/5/edit); свой шаблон из файла DOCX
// правится на экране образца.
import { Button, Textarea, Typography } from '@maxhub/max-ui';
import { useMemo, useRef, useState } from 'react';
import { useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom';

import type { Template } from '@/api/client';
import { Banner } from '@/components/Banner';
import { DocPreview } from '@/components/DocPreview';
import { FieldInput } from '@/components/FieldInput';
import { Page, Section } from '@/components/Page';
import { ErrorState, Loading } from '@/components/StateViews';
import { useAuth } from '@/auth/context';
import { pluralize } from '@/lib/format';
import { errorText, useAsync } from '@/lib/useAsync';
import { useBack } from '@/lib/useBack';
import { haptic, hapticResult } from '@/max/webapp';

import {
  DESCRIPTION_MAX,
  draftFromTemplate,
  EMPTY_DRAFT,
  type EditorDraft,
  fieldsOf,
  insertText,
  marker,
  previewText,
  problemsOf,
  TEXT_MAX,
  TITLE_MAX,
  toRequest,
  withField,
} from './editor';
import { FieldPicker, FieldSettings } from './FieldControls';
import { draftFromTemplate as sampleFromTemplate } from './sample';
import { SampleEditor } from './TemplateSamplePage';

const EXAMPLE = [
  'Акт № {{Номер документа}} от {{Дата документа}}',
  '',
  'Исполнитель: {{Название продавца}}, ИНН {{ИНН продавца}}',
  'Заказчик: {{Название клиента}}',
  '',
  'Работы: {{Выполненные работы}}',
  'Стоимость: {{Сумма}} руб.',
].join('\n');

export function TemplateEditorPage() {
  const { api } = useAuth();
  const param = useParams().templateId;
  const fromParam = useSearchParams()[0].get('from');
  const handed = (useLocation().state as { draft?: EditorDraft } | null)?.draft;
  const editId = param === undefined ? null : Number(param);
  const sourceId = editId ?? (fromParam ? Number(fromParam) : null);
  const back = useBack(editId !== null ? `/create/${editId}` : '/create');
  const state = useAsync<Template | null>(
    () => (sourceId ? api.template(sourceId) : Promise.resolve(null)),
    [api, sourceId],
  );
  const title = editId !== null ? 'Изменить шаблон' : 'Новый шаблон';

  if (sourceId && !state.data) {
    return (
      <Page title={title} onBack={back}>
        {state.loading ? (
          <Loading />
        ) : (
          <ErrorState message={state.error ?? 'Шаблон не найден'} onRetry={state.reload} />
        )}
      </Page>
    );
  }
  // Стандартный шаблон не правится: его «правка» — сохранение своей копии.
  const source = state.data;
  const copy = !source || editId === null || source.is_builtin;
  if (source?.file && !copy) {
    return (
      <SampleEditor initial={sampleFromTemplate(source)} templateId={source.id} onBack={back} />
    );
  }
  return (
    <TemplateEditor
      key={source?.id ?? 'new'}
      title={copy ? 'Новый шаблон' : title}
      initial={source ? draftFromTemplate(source, { copy }) : (handed ?? EMPTY_DRAFT)}
      templateId={copy ? null : source.id}
      onBack={back}
    />
  );
}

interface TemplateEditorProps {
  title: string;
  initial: EditorDraft;
  // null — новый шаблон.
  templateId: number | null;
  onBack: () => void;
}

function TemplateEditor({ title, initial, templateId, onBack }: TemplateEditorProps) {
  const { api } = useAuth();
  const navigate = useNavigate();
  const [draft, setDraft] = useState(initial);
  const [picking, setPicking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const textRef = useRef<HTMLTextAreaElement>(null);
  // Куда вставлять поле: курсор текста запоминается, пока человек жмёт кнопки ниже.
  const selection = useRef({ start: initial.text.length, end: initial.text.length });
  const fields = useMemo(() => fieldsOf(draft), [draft]);

  const remember = () => {
    const element = textRef.current;
    if (element) selection.current = { start: element.selectionStart, end: element.selectionEnd };
  };

  const insert = (label: string) => {
    const { text, caret } = insertText(draft.text, selection.current, marker(label));
    selection.current = { start: caret, end: caret };
    setDraft({ ...draft, text });
    haptic('light');
  };

  const fail = (message: string) => {
    hapticResult('error');
    setError(message);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const save = async () => {
    const problems = problemsOf(draft);
    if (problems.length > 0) {
      fail(problems.join('. '));
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const body = toRequest(draft);
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
      title={title}
      subtitle="Реквизиты сторон подставятся из организации и карточки клиента"
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

      <Section>
        <div className="fields">
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
            hint="Коротко, для чего шаблон"
            onChange={(value) => setDraft({ ...draft, description: value })}
          />
        </div>
      </Section>

      <Section title="Текст документа">
        <div className="fields">
          <div className="field">
            <Textarea
              ref={textRef}
              mode="secondary"
              className="field__box"
              innerClassNames={{ textarea: 'template-text' }}
              aria-label="Текст документа"
              aria-describedby="template-text-note"
              placeholder={EXAMPLE}
              value={draft.text}
              maxLength={TEXT_MAX}
              rows={12}
              onChange={(event) => {
                setDraft({ ...draft, text: event.target.value });
                selection.current = {
                  start: event.target.selectionStart,
                  end: event.target.selectionEnd,
                };
              }}
              onSelect={remember}
              onBlur={remember}
            />
            <Typography.Text
              id="template-text-note"
              variant="description"
              color="tertiary"
              className="field__note"
            >
              Первая строка станет заголовком. Где будет значение — вставьте поле или напишите его
              название в двойных фигурных скобках: {marker('Срок поставки')}.
            </Typography.Text>
          </div>
          <Button
            variant="secondary"
            size="medium"
            stretched
            aria-expanded={picking}
            onClick={() => setPicking(!picking)}
          >
            {picking ? 'Готово' : 'Вставить поле'}
          </Button>
          {picking ? <FieldPicker onInsert={insert} /> : null}
        </div>
      </Section>

      <Section
        title="Поля"
        after={
          fields.length > 0 ? (
            <Typography.Text variant="description" color="tertiary">
              {fields.length} {pluralize(fields.length, 'поле', 'поля', 'полей')}
            </Typography.Text>
          ) : null
        }
      >
        {fields.length === 0 ? (
          <Typography.Text variant="description" color="tertiary" className="field__note">
            Поля появятся здесь, как только вы вставите их в текст.
          </Typography.Text>
        ) : (
          <div className="fields">
            {fields.map((field) => (
              <FieldSettings
                key={field.key}
                field={field}
                onChange={(next) => setDraft(withField(draft, next))}
              />
            ))}
          </div>
        )}
      </Section>

      {draft.text.trim() ? (
        <Section title="Как будет выглядеть">
          <DocPreview text={previewText(draft.text)} marks={false} />
        </Section>
      ) : null}
    </Page>
  );
}
