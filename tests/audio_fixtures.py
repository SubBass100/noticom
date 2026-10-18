"""Small audio files for tests."""

import shutil
import subprocess
import wave

import numpy as np


def write_wav(path, seconds=0.2, rate=22050, channels=2, amp=0.1):
    t = np.arange(int(rate * seconds)) / rate
    tone = (amp * np.sin(2 * np.pi * 880 * t) * 32767).astype("<i2")
    frames = np.repeat(tone, channels)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(frames.tobytes())
    return path


def write_mp3(path, tmp_wav):
    if shutil.which("ffmpeg") is None:
        return None
    write_wav(tmp_wav)
    subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(tmp_wav), str(path)],
        check=True,
    )
    return path
