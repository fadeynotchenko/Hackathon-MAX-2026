import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';
import { z } from 'zod';

import {
  BOT_USER_STARTED,
  BotUserStarted,
  ENVELOPE_VERSION,
  EVENT_PAYLOADS,
  Envelope,
  NOTIFY_USER,
  NotifyUser,
  decodeEvent,
  encodeEvent,
} from './codec.js';

interface JsonSchema {
  required?: string[];
  properties: Record<string, unknown>;
}
interface SchemaFile {
  envelope_version: number;
  envelope: JsonSchema;
  events: Record<string, JsonSchema>;
}

const schema = JSON.parse(
  readFileSync(join(import.meta.dirname, '../../../contracts/events.schema.json'), 'utf8'),
) as SchemaFile;

function zodKeys(shape: z.ZodObject): { all: string[]; required: string[] } {
  const entries = Object.entries(shape.shape);
  return {
    all: entries.map(([k]) => k).sort(),
    required: entries
      .filter(([, v]) => !(v instanceof z.ZodDefault) && !(v instanceof z.ZodOptional))
      .map(([k]) => k)
      .sort(),
  };
}

describe('event contracts match schema.json exported from Python', () => {
  it('envelope version and fields', () => {
    expect(ENVELOPE_VERSION).toBe(schema.envelope_version);
    expect(zodKeys(Envelope).all).toEqual(Object.keys(schema.envelope.properties).sort());
    expect(zodKeys(Envelope).required).toEqual([...(schema.envelope.required ?? [])].sort());
  });

  it('same set of event types', () => {
    expect(Object.keys(EVENT_PAYLOADS).sort()).toEqual(Object.keys(schema.events).sort());
  });

  it.each(Object.keys(EVENT_PAYLOADS))('payload fields of %s', (type) => {
    const zodSchema = EVENT_PAYLOADS[type as keyof typeof EVENT_PAYLOADS];
    const json = schema.events[type];
    expect(json).toBeDefined();
    expect(zodKeys(zodSchema).all).toEqual(Object.keys(json!.properties).sort());
    expect(zodKeys(zodSchema).required).toEqual([...(json!.required ?? [])].sort());
  });
});

describe('codec', () => {
  it('encodes and decodes a notify.user event', () => {
    const encoded = encodeEvent(
      NOTIFY_USER,
      { max_user_id: 7, text: 'hi', format: null },
      'bot',
      new Date('2026-09-16T00:00:00Z'),
    );
    expect(encoded.fields.v).toBe('1');
    const event = decodeEvent('1-0', encoded.fields);
    expect(event.id).toBe(encoded.id);
    expect(event.type).toBe(NOTIFY_USER);
    expect(NotifyUser.parse(event.payload)).toEqual({
      max_user_id: 7,
      text: 'hi',
      format: null,
      buttons: null,
    });
  });

  it('applies defaults for optional payload fields', () => {
    const started = BotUserStarted.parse({ max_user_id: 1, chat_id: 2 });
    expect(started.first_name).toBe('');
    expect(started.username).toBeNull();
    expect(BOT_USER_STARTED).toBe('bot.user_started');
  });

  it('rejects unknown fields and broken envelopes', () => {
    expect(() => NotifyUser.parse({ max_user_id: 1, text: 'x', extra: 1 })).toThrow();
    expect(() => decodeEvent('1-0', { payload: '{}' })).toThrow(/конверт/);
    expect(() =>
      decodeEvent('1-0', { id: 'a', v: '1', type: 'x', payload: 'nope', ts: '', source: '' }),
    ).toThrow(/JSON/);
    expect(() =>
      decodeEvent('1-0', { id: 'a', v: '1', type: 'x', payload: '[1]', ts: '', source: '' }),
    ).toThrow(/объект/);
  });
});
