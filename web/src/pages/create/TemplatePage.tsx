// Шаблон перед созданием: пустой бланк таким, каким он станет PDF, и что
// понадобится для заполнения. Отсюда же — напоминание про реквизиты своей
// организации: без них каждый документ пришлось бы дозаполнять руками.
import { Button, CellHeader, CellList, CellSimple, Typography } from '@maxhub/max-ui';
import { useNavigate, useParams } from 'react-router-dom';

import { Banner } from '@/components/Banner';
import { Page } from '@/components/Page';
import { ErrorState, Loading } from '@/components/StateViews';
import { DocPreview } from '@/components/DocPreview';
import { useAuth } from '@/auth/context';
import { GROUP_TITLE, groupFields } from '@/lib/format';
import { useAsync } from '@/lib/useAsync';

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
  const hasOrganization = organizations.length > 0;
  return (
    <Page
      title={template.title}
      subtitle={template.description}
      onBack={back}
      footer={
        <Button size="large" stretched onClick={() => navigate(`/create/${template.id}/client`)}>
          Заполнить
        </Button>
      }
    >
      <div className="section">
        <DocPreview text={template.preview} marks={false} />
      </div>
      {!hasOrganization ? (
        <div className="section">
          <Banner tone="warning" title="Реквизиты вашей организации не заполнены">
            Заполните их один раз — дальше они подставятся во все документы.
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
                Заполнить реквизиты
              </Button>
            </div>
          </Banner>
        </div>
      ) : null}
      {groupFields(template.fields).map(([group, fields]) => (
        <CellList
          key={group}
          mode="island"
          filled
          header={
            <CellHeader
              after={
                group === 'Продавец' && hasOrganization ? (
                  <Typography.Text variant="description" color="tertiary">
                    из организации
                  </Typography.Text>
                ) : null
              }
            >
              {GROUP_TITLE[group] ?? group}
            </CellHeader>
          }
        >
          {fields.map((field) => (
            <CellSimple
              key={field.key}
              height="compact"
              title={field.label}
              after={
                field.required ? null : (
                  <Typography.Text variant="description" color="tertiary">
                    необязательно
                  </Typography.Text>
                )
              }
            />
          ))}
        </CellList>
      ))}
    </Page>
  );
}
