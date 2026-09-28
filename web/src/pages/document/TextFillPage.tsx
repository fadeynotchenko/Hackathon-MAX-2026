// Заполнить форму текстом: то же сообщение, что пишут боту, — «кому, за что,
// сколько» своими словами. Помощник раскладывает его по полям документа.
import { Button, Textarea } from '@maxhub/max-ui';
import { useState } from 'react';
import { useParams } from 'react-router-dom';

import { Banner } from '@/components/Banner';
import { Page, Section } from '@/components/Page';
import { useAuth } from '@/auth/context';

import { useFillSubmit } from './fillMethods';

// Предел сервера на одно сообщение помощнику.
const MESSAGE_MAX = 4000;

export function TextFillPage() {
  const { api } = useAuth();
  const documentId = Number(useParams().documentId);
  const { back, busy, notice, submit } = useFillSubmit(documentId, 'text');
  const [text, setText] = useState('');
  const message = text.trim();

  return (
    <Page
      title="Заполнить текстом"
      subtitle="Напишите данные обычным сообщением — как в чате с ботом"
      onBack={back}
      footer={
        <Button
          size="large"
          stretched
          loading={busy}
          disabled={!message}
          onClick={() => void submit(() => api.fillFromMessage(documentId, message))}
        >
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
      <Section>
        <Textarea
          aria-label="Данные для документа"
          mode="primary"
          rows={6}
          maxLength={MESSAGE_MAX}
          placeholder="Для ООО «Ромашка», ИНН 7707083893: разработка сайта, 120 000 ₽, оплата до 10 октября"
          value={text}
          disabled={busy}
          onChange={(event) => setText(event.target.value)}
        />
      </Section>
    </Page>
  );
}
