// Заполнить форму голосом: запись с микрофона, как голосовое боту. Помощник
// расшифровывает её и раскладывает сказанное по полям.
//
// Формат записи — первый из тех, что умеет браузер и принимает сервер
// (OGG и WEBM с Opus, M4A у Safari); сервер определяет его по содержимому.
// Запись ограничена двумя минутами: дольше документ не надиктовывают, а файл
// растёт. Где записи нет (браузер без MediaRecorder, мини-апп без доступа к
// микрофону, отказ в разрешении), остаётся готовое голосовое файлом.
import { Button, CellList, Typography } from '@maxhub/max-ui';
import { useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';

import { Banner } from '@/components/Banner';
import { FilePick } from '@/components/FilePick';
import { IconMic, IconStop, IconUpload } from '@/components/icons';
import { Page } from '@/components/Page';
import { useAuth } from '@/auth/context';

import { useFillSubmit } from './fillMethods';

const MAX_SECONDS = 120;
const RECORDING_TYPES = [
  'audio/ogg;codecs=opus',
  'audio/webm;codecs=opus',
  'audio/webm',
  'audio/mp4',
] as const;
const NO_RECORDING = 'Запись с микрофона здесь недоступна';

// Запись с микрофона или выбранный файл (у него есть имя).
interface Clip {
  blob: Blob;
  name?: string;
}

interface Recording {
  recorder: MediaRecorder;
  stream: MediaStream;
  timer: number;
}

function canRecord(): boolean {
  return (
    typeof MediaRecorder !== 'undefined' &&
    typeof navigator.mediaDevices?.getUserMedia === 'function'
  );
}

// undefined — браузер выберет сам.
function recordingType(): string | undefined {
  if (typeof MediaRecorder.isTypeSupported !== 'function') return undefined;
  return RECORDING_TYPES.find((type) => MediaRecorder.isTypeSupported(type));
}

function micProblem(err: unknown): string {
  const name = err instanceof Error || err instanceof DOMException ? err.name : '';
  if (name === 'NotAllowedError' || name === 'SecurityError') return 'Нет доступа к микрофону';
  if (name === 'NotFoundError' || name === 'OverconstrainedError') return 'Микрофон не найден';
  return 'Не удалось включить микрофон';
}

// Микрофон гаснет вместе с записью: иначе индикатор записи в системе горел бы
// и после ухода с экрана.
function release(recording: Recording | null): void {
  if (!recording) return;
  window.clearInterval(recording.timer);
  if (recording.recorder.state !== 'inactive') {
    recording.recorder.ondataavailable = null;
    recording.recorder.onstop = null;
    recording.recorder.stop();
  }
  for (const track of recording.stream.getTracks()) track.stop();
}

function duration(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
}

export function VoiceFillPage() {
  const { api } = useAuth();
  const documentId = Number(useParams().documentId);
  const { back, busy, notice, submit } = useFillSubmit(documentId, 'voice');
  const [problem, setProblem] = useState<string | null>(() => (canRecord() ? null : NO_RECORDING));
  const [phase, setPhase] = useState<'idle' | 'starting' | 'recording'>('idle');
  const [elapsed, setElapsed] = useState(0);
  const [clip, setClip] = useState<Clip | null>(null);
  const recording = useRef<Recording | null>(null);
  // Разрешение на микрофон спрашивается асинхронно: если экран закрыли, пока
  // висел запрос, включённый микрофон надо сразу погасить.
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      release(recording.current);
      recording.current = null;
    };
  }, []);

  const fail = (message: string) => {
    setProblem(message);
    setPhase('idle');
  };

  const start = async () => {
    setPhase('starting');
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
      if (alive.current) fail(micProblem(err));
      return;
    }
    const stopTracks = () => stream.getTracks().forEach((track) => track.stop());
    if (!alive.current) {
      stopTracks();
      return;
    }
    const type = recordingType();
    let recorder: MediaRecorder;
    try {
      recorder = new MediaRecorder(stream, type ? { mimeType: type } : undefined);
    } catch {
      stopTracks();
      fail(NO_RECORDING);
      return;
    }
    const chunks: Blob[] = [];
    const startedAt = Date.now();
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunks.push(event.data);
    };
    recorder.onstop = () => {
      const seconds = Math.min(MAX_SECONDS, Math.round((Date.now() - startedAt) / 1000));
      release(recording.current);
      recording.current = null;
      const blob = new Blob(chunks, { type: recorder.mimeType || type || 'audio/webm' });
      setClip(blob.size > 0 ? { blob } : null);
      setElapsed(seconds);
      setPhase('idle');
    };
    const timer = window.setInterval(() => {
      const seconds = Math.floor((Date.now() - startedAt) / 1000);
      setElapsed(Math.min(seconds, MAX_SECONDS));
      if (seconds >= MAX_SECONDS && recorder.state === 'recording') recorder.stop();
    }, 250);
    recording.current = { recorder, stream, timer };
    try {
      // Кусками по секунде: данные не копятся в одном буфере до остановки.
      recorder.start(1000);
    } catch {
      release(recording.current);
      recording.current = null;
      fail(NO_RECORDING);
      return;
    }
    setClip(null);
    setElapsed(0);
    setPhase('recording');
  };

  const stop = () => {
    const recorder = recording.current?.recorder;
    if (recorder?.state === 'recording') recorder.stop();
  };

  const send = () => {
    if (!clip) return;
    void submit(() => api.voiceIntoDocument(documentId, clip.blob));
  };

  const footer = (
    <Button
      size="large"
      stretched
      loading={busy}
      disabled={!clip || phase !== 'idle'}
      onClick={send}
    >
      Заполнить
    </Button>
  );

  return (
    <Page
      title="Заполнить голосом"
      subtitle="Расскажите, кому документ, за что и на какую сумму — расшифруем и заполним"
      onBack={back}
      footer={footer}
    >
      {notice ? (
        <div className="section">
          <Banner tone={notice.tone} title={notice.title}>
            {notice.text}
          </Banner>
        </div>
      ) : null}
      {problem ? (
        <>
          <div className="section">
            <Banner tone="info" title={problem}>
              Выберите готовое голосовое файлом: OGG, MP3, M4A, WEBM или WAV.
            </Banner>
          </div>
          <CellList mode="island" filled>
            <FilePick
              icon={<IconUpload />}
              title={clip?.name ?? 'Выбрать аудиофайл'}
              subtitle={clip?.name ? 'Нажмите, чтобы выбрать другой' : undefined}
              accept="audio/*"
              busy={busy}
              onPick={(file) => setClip({ blob: file, name: file.name })}
            />
          </CellList>
        </>
      ) : (
        <Recorder
          phase={phase}
          elapsed={elapsed}
          recorded={clip !== null}
          disabled={busy}
          onStart={() => void start()}
          onStop={stop}
        />
      )}
    </Page>
  );
}

interface RecorderProps {
  phase: 'idle' | 'starting' | 'recording';
  elapsed: number;
  recorded: boolean;
  disabled: boolean;
  onStart: () => void;
  onStop: () => void;
}

function Recorder({ phase, elapsed, recorded, disabled, onStart, onStop }: RecorderProps) {
  const recordingNow = phase === 'recording';
  const caption =
    phase === 'starting'
      ? 'Включаем микрофон…'
      : recordingNow
        ? `Идёт запись, до ${duration(MAX_SECONDS)}. Нажмите, чтобы закончить`
        : recorded
          ? 'Запись готова. Нажмите «Заполнить» или запишите заново'
          : 'Нажмите и говорите';
  return (
    <div className="section">
      <div className="recorder">
        <button
          type="button"
          className={`recorder__button${recordingNow ? ' recorder__button--on' : ''}`}
          aria-label={
            recordingNow ? 'Остановить запись' : recorded ? 'Записать заново' : 'Начать запись'
          }
          disabled={disabled || phase === 'starting'}
          onClick={recordingNow ? onStop : onStart}
        >
          {recordingNow ? <IconStop size={32} /> : <IconMic size={36} />}
        </button>
        <Typography.Text variant="header" className="recorder__time">
          {duration(elapsed)}
        </Typography.Text>
        <Typography.Text variant="description" color="secondary" role="status">
          {caption}
        </Typography.Text>
      </div>
    </div>
  );
}
