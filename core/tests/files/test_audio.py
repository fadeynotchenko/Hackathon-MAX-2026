"""Голосовое к WAV для модели: любой формат клиента → PCM 16 кГц моно."""

from __future__ import annotations

import io
import wave

import pytest

from core.files.audio import SAMPLE_RATE, AudioDecodeError, to_speech_wav
from tests.samples import voice_clip


@pytest.mark.parametrize(
    ("container", "codec"),
    [("ogg", "libopus"), ("webm", "libopus"), ("mp3", "libmp3lame"), ("ipod", "aac")],
)
async def test_voice_becomes_speech_wav(container: str, codec: str) -> None:
    data = await to_speech_wav(voice_clip(container, codec, seconds=1.0))

    with wave.open(io.BytesIO(data)) as wav:
        assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) == (1, 2, SAMPLE_RATE)
        seconds = wav.getnframes() / SAMPLE_RATE
    # Кодеки добавляют задержку в начале и добивают последний кадр.
    assert seconds == pytest.approx(1.0, abs=0.1)


@pytest.mark.parametrize(
    "data",
    [b"OggS\x00\x02" + b"\x00" * 64, b"\x1a\x45\xdf\xa3" + b"\x00" * 64, b""],
    ids=["ogg-signature-only", "webm-signature-only", "empty"],
)
async def test_signature_without_sound_is_rejected(data: bytes) -> None:
    with pytest.raises(AudioDecodeError):
        await to_speech_wav(data)
