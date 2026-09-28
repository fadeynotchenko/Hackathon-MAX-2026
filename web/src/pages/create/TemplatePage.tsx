// Шаблон перед созданием: пустой бланк таким, каким он станет PDF, и одна
// кнопка. Список полей не нужен — они видны на самом бланке. «Заполнить» сразу
// создаёт черновик и открывает форму: продавцом сервер ставит основную
// организацию, клиента вписывают в самой форме — отдельный шаг «Для кого
// документ?» только удлинял путь. Свой шаблон здесь меняют и удаляют,
// стандартный — берут за основу своего.
import { Button, CellAction, CellList, CellSimple } from '@maxhub/max-ui';
import { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import type { Template } from '@/api/client';
import { Banner } from '@/components/Banner';
import { IconCopy, IconEdit, IconTrash } from '@/components/icons';
import { Page } from '@/components/Page';
import { ErrorState, Loading } from '@/components/StateViews';
import { DocPreview } from '@/components/DocPreview';
import { useAuth } from '@/auth/context';
import { errorText, useAsync } from '@/lib/useAsync';
import { useBack } from '@/lib/useBack';

export function TemplatePage() {
  const { api } = useAuth();
  const navigate = useNavigate();
  const templateId = Number(useParams().templateId);
  const state = useAsync(() => api.template(templateId), [api, templateId]);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Второй тап может прийти раньше перерисовки с `loading` — без ref вышло бы
  // два черновика.
  const busy = useRef(false);
  // Ушли «Назад», пока черновик создавался, — в его форму уже не ведём.
  const mounted = useRef(false);
  const back = useBack('/create');

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const fill = async (template: Template) => {
    if (busy.current) return;
    busy.current = true;
    setCreating(true);
    setError(null);
    try {
      const document = await api.createDocument({ template_id: template.id });
      if (!mounted.current) return;
      // Обычный переход, не replace: «Назад» из формы вернёт к шаблону,
      // и он снова готов создать черновик.
      void navigate(`/documents/${document.id}/fill`);
      busy.current = false;
      setCreating(false);
    } catch (err) {
      if (!mounted.current) return;
      setError(errorText(err, 'Не удалось создать документ'));
      busy.current = false;
      setCreating(false);
    }
  };

  if (state.loading) {
    return (
      <Page title="Шаблон" onBack={back}>
        <Loading />
      </Page>
    );
  }
  if (!state.data) {
    return (
      <Page title="Шаблон" onBack={back}>
        <ErrorState message={state.error ?? 'Шаблон не найден'} onRetry={state.reload} />
      </Page>
    );
  }

  const template = state.data;
  return (
    <Page
      title={template.title}
      onBack={back}
      footer={
        <Button size="large" stretched loading={creating} onClick={() => void fill(template)}>
          Заполнить
        </Button>
      }
    >
      {error ? (
        <div className="section">
          <Banner tone="error" title={error} />
        </div>
      ) : null}
      <div className="section">
        <DocPreview text={template.preview} marks={false} />
      </div>
      {template.file ? (
        <div className="section">
          <Banner
            tone="info"
            title={
              template.is_builtin
                ? 'Соберётся в бланке DOCX'
                : `Соберётся в файле «${template.file.filename}»`
            }
          >
            Таблицы, линейки и шрифты — как в образце; выше — только текст.
          </Banner>
        </div>
      ) : null}
      <TemplateActions template={template} onGone={back} />
    </Page>
  );
}

// Удалённый шаблон закрывает экран шагом назад: каталог под ним в стеке
// обновится сам, а замена адресом оставила бы под новым каталогом прежний.
function TemplateActions({ template, onGone }: { template: Template; onGone: () => void }) {
  const { api } = useAuth();
  const navigate = useNavigate();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (template.is_builtin) {
    return (
      <CellList mode="island" filled>
        <CellSimple
          title="Создать свой шаблон на основе этого"
          subtitle="Свои названия полей и значения — стандартный останется как есть"
          before={<IconCopy />}
          showChevron
          onClick={() => navigate(`/templates/new?from=${template.id}`)}
        />
      </CellList>
    );
  }

  const remove = async () => {
    if (!confirmDelete) {
      setConfirmDelete(true);
      return;
    }
    if (deleting) return;
    setDeleting(true);
    try {
      await api.deleteTemplate(template.id);
      onGone();
    } catch (err) {
      setError(errorText(err, 'Не удалось удалить шаблон'));
      setDeleting(false);
    }
  };

  return (
    <>
      {error ? (
        <div className="section">
          <Banner tone="error" title={error} />
        </div>
      ) : null}
      <CellList mode="island" filled>
        <CellSimple
          title="Изменить шаблон"
          subtitle="Созданные документы сохранят прежний текст"
          before={<IconEdit />}
          showChevron
          onClick={() => navigate(`/templates/${template.id}/edit`)}
        />
        <CellAction
          before={<IconTrash />}
          mode="destructive"
          disabled={deleting}
          onClick={() => void remove()}
        >
          {confirmDelete ? 'Нажмите ещё раз, чтобы удалить' : 'Удалить шаблон'}
        </CellAction>
      </CellList>
    </>
  );
}
