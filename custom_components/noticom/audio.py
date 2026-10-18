"""Chime audio conversion: any WAV/MP3 to normalized mono 16-bit WAV.

HA-independent so it can be unit-tested. WAVs are decoded natively; MP3s
(and WAV encodings Python's wave module can't read) go through ffmpeg,
which Home Assistant OS ships with.
"""

from __future__ import annotations

import io
import subprocess
import wave
from pathlib import Path

import numpy as np

FFMPEG_RATE = 44100
TARGET_PEAK = 0.89  # about -1 dBFS
MAX_BOOST = 10.0  # +20 dB; chimes are produced audio, so rarely needed
SILENCE_PEAK = 0.001


class ConversionError(Exception):
    """The file couldn't be decoded."""


def _decode_wav(path: Path) -> tuple[np.ndarray, int]:
    """Decode a PCM WAV to float mono in [-1, 1]."""
    with wave.open(str(path), "rb") as wav:
        channels, width, rate = wav.getnchannels(), wav.getsampwidth(), wav.getframerate()
        raw = wav.readframes(wav.getnframes())
    if width == 1:
        samples = (np.frombuffer(raw, np.uint8).astype(np.float32) - 128) / 128
    elif width == 2:
        samples = np.frombuffer(raw, "<i2").astype(np.float32) / 32768
    elif width == 3:
        b = np.frombuffer(raw, np.uint8).reshape(-1, 3).astype(np.int32)
        ints = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        ints = np.where(ints & 0x800000, ints - 0x1000000, ints)
        samples = ints.astype(np.float32) / 8388608
    elif width == 4:
        samples = np.frombuffer(raw, "<i4").astype(np.float32) / 2147483648
    else:
        raise ConversionError(f"unsupported WAV sample width {width}")
    usable = samples.size - samples.size % channels
    return samples[:usable].reshape(-1, channels).mean(axis=1), rate


def _decode_ffmpeg(path: Path) -> tuple[np.ndarray, int]:
    """Decode anything ffmpeg understands to float mono at FFMPEG_RATE."""
    try:
        proc = subprocess.run(
            [
                "ffmpeg", "-nostdin", "-v", "error", "-i", str(path),
                "-f", "s16le", "-ac", "1", "-ar", str(FFMPEG_RATE), "-",
            ],
            capture_output=True,
            timeout=60,
            check=False,
        )
    except FileNotFoundError as err:
        raise ConversionError("ffmpeg is not installed") from err
    except subprocess.TimeoutExpired as err:
        raise ConversionError("ffmpeg timed out") from err
    if proc.returncode != 0 or not proc.stdout:
        raise ConversionError(proc.stderr.decode(errors="replace").strip() or "ffmpeg failed")
    return np.frombuffer(proc.stdout, "<i2").astype(np.float32) / 32768, FFMPEG_RATE


def decode(path: Path) -> tuple[np.ndarray, int]:
    """Decode a chime file to (float mono samples, sample rate)."""
    if path.suffix.lower() == ".wav":
        try:
            return _decode_wav(path)
        except (wave.Error, EOFError, ConversionError):
            pass  # e.g. float or WAVE_FORMAT_EXTENSIBLE: let ffmpeg try
    return _decode_ffmpeg(path)


def normalize(samples: np.ndarray) -> np.ndarray:
    """Remove DC offset and scale the peak to TARGET_PEAK (up or down)."""
    if samples.size == 0:
        return samples
    samples = samples - samples.mean()
    peak = float(np.abs(samples).max())
    if peak < SILENCE_PEAK:
        return samples
    return samples * min(TARGET_PEAK / peak, MAX_BOOST)


def encode_wav(samples: np.ndarray, rate: int) -> bytes:
    """Encode float mono as 16-bit mono WAV bytes."""
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2").tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(pcm)
    return buf.getvalue()


def convert(path: Path) -> bytes:
    """Chime file -> normalized mono 16-bit WAV bytes."""
    samples, rate = decode(path)
    if samples.size == 0:
        raise ConversionError("no audio")
    return encode_wav(normalize(samples), rate)
