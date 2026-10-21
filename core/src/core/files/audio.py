"""Голосовое к виду, который модель читает надёжно: WAV, 16 кГц, моно, 16 бит.

GigaChat принимает файлы разных форматов, но читает их по-разному. Проверено
на живом API (2026-10-04): OGG, M4A и WAV расшифровываются за 1–2 с, WEBM
(его пишет MediaRecorder в Chrome и Яндекс.Браузере, то есть мини-апп в
веб-клиенте MAX) то проходит, то даёт зацикленную расшифровку до таймаута,
а на MP3 ответ не приходит вовсе. Поэтому до модели доходит только PCM:
формат клиента нам не подконтролен, а одна форма входа убирает разброс.

16 кГц моно — частота распознавания речи: больше модель не использует, а
двухминутная запись укладывается в 4 МБ. Декодирует PyAV — ffmpeg внутри
колеса, без системного пакета и лишних минут сборки образа.
"""

from __future__ import annotations

import asyncio
import io
import wave

import av
import av.error

SAMPLE_RATE = 16_000
SAMPLE_WIDTH = 2


class AudioDecodeError(Exception):
    """Файл похож на аудио по сигнатуре, но не декодируется."""


def _samples(frame: av.AudioFrame) -> bytes:
    # Буфер плоскости выровнен и бывает длиннее данных: хвост — мусор, а не тишина.
    return bytes(frame.planes[0])[: frame.samples * SAMPLE_WIDTH]


def _to_wav(data: bytes) -> bytes:
    pcm = bytearray()
    try:
        with av.open(io.BytesIO(data)) as container:
            if not container.streams.audio:
                raise AudioDecodeError("в файле нет звуковой дорожки")
            resampler = av.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
            for frame in container.decode(audio=0):
                for chunk in resampler.resample(frame):
                    pcm += _samples(chunk)
            for chunk in resampler.resample(None):
                pcm += _samples(chunk)
    except av.error.FFmpegError as exc:
        raise AudioDecodeError(str(exc)) from exc
    if not pcm:
        raise AudioDecodeError("в файле нет звука")
    out = io.BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(SAMPLE_WIDTH)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(bytes(pcm))
    return out.getvalue()


async def to_speech_wav(data: bytes) -> bytes:
    """Декодировать голосовое любого поддержанного формата в WAV для модели.
    Декодирование — работа процессора, поэтому в потоке, а не в цикле событий."""
    return await asyncio.to_thread(_to_wav, data)
