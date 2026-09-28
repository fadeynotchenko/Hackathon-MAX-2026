// Заполнить форму с фото или скана: карточка предприятия, счёт, договор —
// то же, что принимает бот. Файл выбирается отдельно от отправки, чтобы к нему
// можно было дописать подсказку («это реквизиты покупателя»): без неё
// реквизиты с чужого счёта легко принять за свои.
import { Button, CellList, Input, Typography } from '@maxhub/max-ui';
import { useId, useState } from 'react';
import { useParams } from 'react-router-dom';

import { Banner } from '@/components/Banner';
import { FilePick } from '@/components/FilePick';
import { IconCamera } from '@/components/icons';
import { Page, Section } from '@/components/Page';
import { useAuth } from '@/auth/context';

import { useFillSubmit } from './fillMethods';

// Предел сервера на подсказку к файлу.
const HINT_MAX = 500;

export function PhotoFillPage() {
  const { api } = useAuth();
  const documentId = Number(useParams().documentId);
  const { back, busy, notice, submit } = useFillSubmit(documentId, 'photo');
  const [file, setFile] = useState<File | null>(null);
  const [hint, setHint] = useState('');
  const hintId = useId();

  const recognize = () => {
    if (!file) return;
    void submit(() => api.recognizeIntoDocument(documentId, file, hint.trim() || undefined));
  };

  return (
    <Page
      title="Заполнить с фото"
      subtitle="Фото карточки предприятия, счёта или договора, скан в PDF или DOCX"
      onBack={back}
      footer={
        <Button size="large" stretched loading={busy} disabled={!file} onClick={recognize}>
          Заполнить
        </Button>
      }
    >
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
          title={file ? file.name : 'Выбрать фото или скан'}
          subtitle={file ? 'Нажмите, чтобы выбрать другой' : 'Камера, галерея или файл'}
          busy={busy}
          onPick={setFile}
        />
      </CellList>
      <Section>
        <div className="fields">
          <div className="field">
            <div className="field__label">
              <Typography.Text variant="description-strong" color="secondary" asChild>
                <label htmlFor={hintId}>Подсказка · необязательно</label>
              </Typography.Text>
            </div>
            <Input
              id={hintId}
              className="field__box"
              placeholder="Что на файле — например, реквизиты покупателя"
              maxLength={HINT_MAX}
              value={hint}
              disabled={busy}
              onChange={(event) => setHint(event.target.value)}
            />
          </div>
        </div>
      </Section>
    </Page>
  );
}
