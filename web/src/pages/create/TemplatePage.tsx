// Шаблон перед созданием: пустой бланк таким, каким он станет PDF, и одна
// кнопка. Список полей не нужен — они видны на самом бланке. Отсюда же —
// напоминание про реквизиты своей организации: без них каждый документ
// пришлось бы дозаполнять руками. Свой шаблон здесь меняют и удаляют,
// стандартный — берут за основу своего.
import { Button, CellAction, CellList, CellSimple } from '@maxhub/max-ui';
import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import type { Template } from '@/api/client';
import { Banner } from '@/components/Banner';
import { IconCopy, IconEdit, IconTrash } from '@/components/icons';
import { Page } from '@/components/Page';
import { ErrorState, Loading } from '@/components/StateViews';
import { DocPreview } from '@/components/DocPreview';
import { useAuth } from '@/auth/context';
import { errorText, useAsync } from '@/lib/useAsync';

export function TemplatePage() {
  const { api } = useAuth();
  const navigate = useNavigate();
  const templateId = Number(useParams().templateId);
  const state = useAsync(
    () => Promise.all([api.template(templateId), api.organizations()]),
    [api, templateId],
  );
  const back = () => navigate('/create');

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

  const [template, organizations] = state.data;
  return (
    <Page
      title={template.title}
      onBack={back}
      footer={
        <Button size="large" stretched onClick={() => navigate(`/create/${template.id}/client`)}>
          Заполнить
        </Button>
      }
    >
      {organizations.length === 0 ? (
        <div className="section">
          <Banner tone="warning" title="Добавьте свои реквизиты">
            Один раз — и они будут во всех документах.
            <div style={{ marginTop: 8 }}>
              <Button
                size="small"
                variant="secondary"
                onClick={() =>
                  navigate('/profile/organizations/new', {
                    state: { returnTo: `/create/${template.id}` },
                  })
                }
              >
                Добавить
              </Button>
            </div>
          </Banner>
        </div>
      ) : null}
      <div className="section">
        <DocPreview text={template.preview} marks={false} />
      </div>
      {template.file ? (
        <div className="section">
          <Banner tone="info" title={`Соберётся в файле «${template.file.filename}»`}>
            С оформлением образца; выше — только текст.
          </Banner>
        </div>
      ) : null}
      <TemplateActions template={template} />
    </Page>
  );
}

function TemplateActions({ template }: { template: Template }) {
  const { api } = useAuth();
  const navigate = useNavigate();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (template.is_builtin) {
    return (
      <CellList mode="island" filled>
        <CellSimple
          title="Сделать свой на основе этого"
          subtitle="Поменяйте текст под себя — стандартный останется как есть"
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
      void navigate('/create', { replace: true });
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
