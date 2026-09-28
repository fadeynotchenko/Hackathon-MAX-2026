// Лист документа картинкой: страницы того же PDF, что уходит в чат (сервер
// рисует их из бланка). Так видно настоящее оформление — таблицы, линии, шрифты,
// — а не только текст. Пока картинка грузится — пустой белый лист того же
// размера: текст на его месте выглядел как «моковая рыба», которую потом
// подменяет настоящая. Текстовый лист DocPreview — только если картинку не
// нарисовать (локальный стенд без LibreOffice).
//
// Картинки кешируются на время сессии по источнику и версии: каталог и экран
// шаблона не просят один и тот же бланк дважды, а правка документа меняет
// версию и даёт свежий лист.
import { useEffect, useState } from 'react';

import type { ApiClient, PreviewSize, PreviewSource } from '@/api/client';
import { useAuth } from '@/auth/context';

import { DocPreview } from './DocPreview';

interface LoadedPage {
  url: string;
  pages: number;
}

const CACHE_LIMIT = 80;
const cache = new Map<string, Promise<LoadedPage>>();

function loadPage(
  api: ApiClient,
  source: PreviewSource,
  version: string,
  page: number,
  size: PreviewSize,
): Promise<LoadedPage> {
  const key = `${source.kind}:${source.id}:${version}:${size}:${page}`;
  const cached = cache.get(key);
  if (cached) return cached;
  const loading = api.previewPage(source, page, size).then(({ image, pages }) => ({
    url: URL.createObjectURL(image),
    pages,
  }));
  // Неудачу не кешируем: следующий показ попробует снова.
  loading.catch(() => cache.delete(key));
  cache.set(key, loading);
  if (cache.size > CACHE_LIMIT) {
    const [oldest] = cache.keys();
    if (oldest !== undefined) {
      void cache
        .get(oldest)
        ?.then((stale) => URL.revokeObjectURL(stale.url))
        .catch(() => undefined);
      cache.delete(oldest);
    }
  }
  return loading;
}

export interface SheetPreviewProps {
  source: PreviewSource;
  // Меняется вместе с содержимым: у документа — updated_at.
  version: string;
  // Текстовый лист на время загрузки и если картинку не нарисовать.
  text: string;
  marks?: boolean;
  mini?: boolean;
}

export function SheetPreview({
  source,
  version,
  text,
  marks = true,
  mini = false,
}: SheetPreviewProps) {
  const { api } = useAuth();
  const size: PreviewSize = mini ? 'thumb' : 'page';
  const [pages, setPages] = useState<{ key: string; urls: string[] } | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const key = `${source.kind}:${source.id}:${version}:${size}`;

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const first = await loadPage(api, source, version, 1, size);
        if (cancelled) return;
        setPages({ key, urls: [first.url] });
        // Миниатюре хватает первой страницы; листу во весь экран — все.
        if (mini || first.pages < 2) return;
        const rest = await Promise.all(
          Array.from({ length: first.pages - 1 }, (_, index) =>
            loadPage(api, source, version, index + 2, size),
          ),
        );
        if (!cancelled) setPages({ key, urls: [first.url, ...rest.map((item) => item.url)] });
      } catch {
        // Лист картинкой — улучшение, а не условие: остаётся текстовый.
        if (!cancelled) setFailed(key);
      }
    })();
    return () => {
      cancelled = true;
    };
    // source — новый объект на каждый рендер; экран определяют его поля в key.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api, key]);

  const urls = pages?.key === key ? pages.urls : null;
  if (!urls && failed === key) return <DocPreview text={text} marks={marks} mini={mini} />;
  if (!urls) {
    return (
      <div className={`sheet sheet--image${mini ? ' sheet--mini' : ''}`} aria-busy="true">
        <div className="sheet__image sheet__image--loading" />
      </div>
    );
  }
  return (
    <div className={`sheet sheet--image${mini ? ' sheet--mini' : ''}`}>
      {urls.map((url, index) => (
        <img
          key={url}
          className="sheet__image"
          src={url}
          alt={mini || index > 0 ? '' : 'Предпросмотр документа'}
          aria-hidden={mini || undefined}
          draggable={false}
        />
      ))}
    </div>
  );
}
