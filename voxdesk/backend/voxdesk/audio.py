import asyncio
import tempfile
import wave
from pathlib import Path

import numpy as np

from .schemas import AppError


async def process_audio(raw: bytes, max_seconds: int = 60) -> bytes:
    """Decode untrusted media with bounded ffmpeg process time and output duration."""
    if not raw:
        raise AppError("empty_audio", "The recording is empty. Please record again.", 422)
    with tempfile.TemporaryDirectory(prefix="voxdesk-") as directory:
        source, target = Path(directory) / "input", Path(directory) / "output.wav"
        source.write_bytes(raw)
        try:
            process = await asyncio.create_subprocess_exec(
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-threads",
                "1",
                "-protocol_whitelist",
                "file,pipe",
                "-format_whitelist",
                "wav,mp3,matroska,webm,mov,ogg,flac,aac",
                "-i",
                str(source),
                "-t",
                str(max_seconds + 1),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "pcm_s16le",
                str(target),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise AppError(
                "audio_unavailable", "FFmpeg is not installed on the server.", 503
            ) from exc
        try:
            _, _stderr = await asyncio.wait_for(process.communicate(), timeout=15)
        except BaseException:
            if process.returncode is None:
                process.kill()
                await process.wait()
            raise
        if process.returncode != 0 or not target.exists():
            raise AppError(
                "invalid_audio", "This file is not readable audio. Try WAV, WebM, MP3 or M4A.", 422
            )
        with wave.open(str(target), "rb") as recording:
            duration = recording.getnframes() / recording.getframerate()
            samples = np.frombuffer(
                recording.readframes(recording.getnframes()), dtype=np.int16
            ).astype(float)
        if duration > max_seconds + 0.02:
            raise AppError(
                "audio_too_long", f"Recordings must be {max_seconds} seconds or shorter.", 413
            )
        if duration < 0.25 or not len(samples) or np.sqrt(np.mean(samples**2)) < 35:
            raise AppError(
                "no_speech",
                "The recording is silent or too short. Speak closer to the microphone.",
                422,
            )
        return target.read_bytes()
