// Документ по своему файлу: договор от партнёра, прошлый счёт, анкета — то,
// чего нет в каталоге. Сервер находит в файле места для данных (метки {{…}},
// помощник или линейки и реквизиты) и сразу создаёт документ, где значения
// полей — как в файле. Дальше обычный путь: форма → проверка → отправка;
// DOCX собирается в копии присланного файла, из PDF переносится только текст.
import { CellList } from '@maxhub/max-ui';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import type { DocumentImport } from '@/api/client';
import { Banner } from '@/components/Banner';
import { FilePick } from '@/components/FilePick';
import { IconUpload } from '@/components/icons';
import { Page } from '@/components/Page';
import { useAuth } from '@/auth/context';
import { errorText } from '@/lib/useAsync';
import { useBack } from '@/lib/useBack';
import { hapticResult } from '@/max/webapp';

import { fillFormPath, leaveNotice } from './fillMethods';
import { importNotice } from './imported';

const DOCUMENT_TYPES =
  'application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,.docx,.pdf';

export function ImportPage() {
  const { api } = useAuth();
  const navigate = useNavigate();
  const back = useBack('/create');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const pick = async (file: File) => {
    setBusy(true);
    setError(null);
    try {
      const result: DocumentImport = await api.importDocument(file);
      hapticResult('success');
      // Плашку «что нашлось» форма покажет тем же путём, что итог фото и голоса.
      leaveNotice(result.document.id, importNotice(result));
      void navigate(fillFormPath(result.document.id), { replace: true });
    } catch (err) {
      hapticResult('error');
      setError(errorText(err, 'Не удалось прочитать файл'));
      setBusy(false);
    }
  };

  return (
    <Page title="Документ из файла" subtitle="Поменяем данные, оформление останется" onBack={back}>
      {error ? (
        <div className="section">
          <Banner tone="error" title={error} />
        </div>
      ) : null}
      <CellList mode="island" filled>
        <FilePick
          icon={<IconUpload />}
          title="Выбрать DOCX или PDF"
          subtitle="Договор, счёт, акт — любой ваш документ"
          busy={busy}
          busyTitle="Ищем данные в файле…"
          accept={DOCUMENT_TYPES}
          onPick={(file) => void pick(file)}
        />
      </CellList>
      <div className="section">
        <Banner tone="info" title="Как это работает">
          Найдём в файле то, что меняется от документа к документу: стороны, суммы, даты, реквизиты.
          Вы поправите значения в форме, а файл соберётся заново — с тем же логотипом, таблицами и
          шрифтами. Из PDF переносится только текст, поэтому лучше DOCX.
        </Banner>
      </div>
    </Page>
  );
}
