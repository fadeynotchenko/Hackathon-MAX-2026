import { afterEach, describe, expect, it, vi } from 'vitest';

import { silentLogger } from '../logger.js';
import { DOCUMENT_READY, NOTIFY_USER } from './codec.js';
import { HandlerRejected } from './consumer.js';
import { coreEventHandlers } from './handlers.js';

function setup(sendImpl: () => Promise<unknown>, markerSet = 'OK') {
  const sendMessageToUser = vi.fn().mockImplementation(sendImpl);
  const redis = { set: vi.fn().mockResolvedValue(markerSet), del: vi.fn().mockResolvedValue(1) };
  const handlers = coreEventHandlers(
    { api: { sendMessageToUser } } as never,
    redis as never,
    silentLogger(),
    { coreApiUrl: 'http://api:8000' },
  );
  const event = {
    id: 'evt-1',
    v: 1,
    type: NOTIFY_USER,
    payload: { max_user_id: 5, text: 'hi', format: null },
    ts: '',
    source: 'api',
    streamId: '1-0',
  };
  return { sendMessageToUser, redis, handler: handlers[NOTIFY_USER]!, event };
}

describe('notify.user handler', () => {
  it('sends once and records the event id', async () => {
    const { handler, event, sendMessageToUser, redis } = setup(() => Promise.resolve({}));
    await handler(event);
    expect(sendMessageToUser).toHaveBeenCalledWith(5, 'hi', {});
    expect(redis.set).toHaveBeenCalledWith(
      'events:delivered:evt-1',
      '1',
      'EX',
      expect.any(Number),
      'NX',
    );
  });

  it('skips a redelivered event without sending', async () => {
    const { handler, event, sendMessageToUser } = setup(() => Promise.resolve({}), null as never);
    await handler(event);
    expect(sendMessageToUser).not.toHaveBeenCalled();
  });

  it('clears the marker and rejects permanently on 403', async () => {
    const { handler, event, redis } = setup(() =>
      Promise.reject(Object.assign(new Error('blocked'), { status: 403 })),
    );
    await expect(handler(event)).rejects.toBeInstanceOf(HandlerRejected);
    expect(redis.del).toHaveBeenCalledWith('events:delivered:evt-1');
  });

  it('clears the marker and rethrows transient errors', async () => {
    const { handler, event, redis } = setup(() => Promise.reject(new Error('timeout')));
    await expect(handler(event)).rejects.toThrow('timeout');
    expect(redis.del).toHaveBeenCalledTimes(1);
  });
});

function documentSetup(options: {
  fetchImpl: typeof fetch;
  uploadImpl?: () => Promise<{ toJson: () => object }>;
  sendImpl?: () => Promise<unknown>;
  markerSet?: string | null;
  miniAppName?: string;
}) {
  const uploadFile = vi
    .fn()
    .mockImplementation(
      options.uploadImpl ?? (() => Promise.resolve({ toJson: () => ({ type: 'file' }) })),
    );
  const sendMessageToUser = vi
    .fn()
    .mockImplementation(options.sendImpl ?? (() => Promise.resolve({})));
  const redis = {
    set: vi.fn().mockResolvedValue(options.markerSet === undefined ? 'OK' : options.markerSet),
    del: vi.fn().mockResolvedValue(1),
  };
  vi.stubGlobal('fetch', options.fetchImpl);
  const documentDelivery = vi.fn().mockResolvedValue('evt-report');
  const handlers = coreEventHandlers(
    { api: { uploadFile, sendMessageToUser } } as never,
    redis as never,
    silentLogger(),
    {
      coreApiUrl: 'http://api:8000',
      publisher: { documentDelivery },
      ...(options.miniAppName ? { miniAppName: options.miniAppName } : {}),
    },
  );
  const event = {
    id: 'evt-doc-1',
    v: 1,
    type: DOCUMENT_READY,
    payload: {
      max_user_id: 5,
      document_id: 42,
      title: 'КП для Клиента',
      filename: 'КП для Клиента.docx',
      format: 'docx',
      size: 1024,
      download_token: 'a'.repeat(32),
      text: 'файл во вложении',
    },
    ts: '',
    source: 'api',
    streamId: '1-0',
  };
  return {
    uploadFile,
    sendMessageToUser,
    redis,
    documentDelivery,
    handler: handlers[DOCUMENT_READY]!,
    event,
  };
}

describe('document.ready handler', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('downloads by token, uploads under the real filename and sends it', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(new Uint8Array([0x50, 0x4b])));
    const { handler, event, uploadFile, sendMessageToUser } = documentSetup({
      fetchImpl: fetchMock as never,
    });

    await handler(event);

    expect(fetchMock).toHaveBeenCalledWith(
      `http://api:8000/api/v1/documents/download/${'a'.repeat(32)}`,
      expect.objectContaining({ signal: expect.anything() }),
    );
    const source = (uploadFile.mock.calls[0]?.[0] as { source: string }).source;
    expect(source.endsWith('КП для Клиента.docx')).toBe(true);
    expect(sendMessageToUser).toHaveBeenCalledWith(5, 'файл во вложении', {
      attachments: [{ type: 'file' }],
    });
  });

  it('adds a button that opens the document card in the mini app', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(new Uint8Array([0x50, 0x4b])));
    const { handler, event, sendMessageToUser } = documentSetup({
      fetchImpl: fetchMock as never,
      miniAppName: 't409_hakaton_max_bot',
    });

    await handler(event);

    const extra = sendMessageToUser.mock.calls[0]?.[2] as {
      attachments: [unknown, { payload: { buttons: unknown[][] } }];
    };
    expect(extra.attachments[0]).toEqual({ type: 'file' });
    expect(extra.attachments[1].payload.buttons).toEqual([
      [
        {
          type: 'open_app',
          text: '📱 Открыть в приложении',
          web_app: 't409_hakaton_max_bot',
          payload: 'doc_42',
        },
      ],
    ]);
  });

  it('reports the delivery to core with the document.ready event id', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(new Uint8Array([0x50, 0x4b])));
    const { handler, event, documentDelivery } = documentSetup({ fetchImpl: fetchMock as never });

    await handler(event);

    expect(documentDelivery).toHaveBeenCalledWith({
      max_user_id: 5,
      document_id: 42,
      event_id: 'evt-doc-1',
      format: 'docx',
      status: 'delivered',
      error: null,
    });
  });

  it('reports a failed upload with the MAX status code', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(new Uint8Array([0x50, 0x4b])));
    const { handler, event, documentDelivery } = documentSetup({
      fetchImpl: fetchMock as never,
      uploadImpl: () => Promise.reject(Object.assign(new Error('forbidden'), { status: 403 })),
    });

    await expect(handler(event)).rejects.toBeInstanceOf(HandlerRejected);
    expect(documentDelivery).toHaveBeenCalledWith(
      expect.objectContaining({ status: 'failed', error: 'max_api.403' }),
    );
  });

  it('gives up on a burnt token instead of retrying forever', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('no', { status: 404 }));
    const { handler, event, uploadFile, documentDelivery } = documentSetup({
      fetchImpl: fetchMock as never,
    });

    await expect(handler(event)).rejects.toBeInstanceOf(HandlerRejected);
    expect(uploadFile).not.toHaveBeenCalled();
    expect(documentDelivery).toHaveBeenCalledWith(
      expect.objectContaining({ status: 'failed', error: 'document.token_invalid' }),
    );
  });

  it('retries when core is unreachable', async () => {
    const fetchMock = vi.fn().mockRejectedValue(new Error('ECONNREFUSED'));
    const { handler, event, redis } = documentSetup({ fetchImpl: fetchMock as never });

    await expect(handler(event)).rejects.toThrow('ECONNREFUSED');
    expect(redis.del).toHaveBeenCalledWith('events:delivered:evt-doc-1');
  });

  it('skips a redelivered document event', async () => {
    const fetchMock = vi.fn();
    const { handler, event } = documentSetup({ fetchImpl: fetchMock as never, markerSet: null });

    await handler(event);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe('notify.user buttons', () => {
  it('renders core buttons as a callback keyboard', async () => {
    const { handler, event, sendMessageToUser } = setup(() => Promise.resolve({}));
    await handler({
      ...event,
      payload: {
        max_user_id: 5,
        text: 'Проверьте значения',
        format: null,
        buttons: [[{ text: 'Всё верно', payload: 'doc:confirm:12' }]],
      },
    });
    const extra = sendMessageToUser.mock.calls[0]?.[2] as {
      attachments: { payload: { buttons: { type: string; text: string; payload: string }[][] } }[];
    };
    expect(extra.attachments[0]?.payload.buttons).toEqual([
      [expect.objectContaining({ type: 'callback', text: 'Всё верно', payload: 'doc:confirm:12' })],
    ]);
  });

  it('remembers the HTML of a message with buttons, so a tap does not strip the bold', async () => {
    const { handler, event, redis } = setup(() =>
      Promise.resolve({ body: { mid: 'mid.7', text: 'Счёт' } }),
    );
    await handler({
      ...event,
      payload: {
        max_user_id: 5,
        text: '<b>Счёт</b>',
        format: 'html',
        buttons: [[{ text: 'Всё верно', payload: 'doc:confirm:12' }]],
      },
    });
    expect(redis.set).toHaveBeenCalledWith(
      'messages:markup:mid.7',
      JSON.stringify({ text: '<b>Счёт</b>', format: 'html' }),
      'EX',
      expect.any(Number),
    );
  });

  it('delivers once even if the markup cannot be saved', async () => {
    const { handler, event, redis, sendMessageToUser } = setup(() =>
      Promise.resolve({ body: { mid: 'mid.8' } }),
    );
    redis.set.mockImplementation((key: string) =>
      key.startsWith('messages:markup:')
        ? Promise.reject(new Error('down'))
        : Promise.resolve('OK'),
    );
    await handler({
      ...event,
      payload: {
        max_user_id: 5,
        text: '<b>Счёт</b>',
        format: 'html',
        buttons: [[{ text: 'Всё верно', payload: 'doc:confirm:12' }]],
      },
    });
    expect(sendMessageToUser).toHaveBeenCalledTimes(1);
    expect(redis.del).not.toHaveBeenCalled();
  });
});
