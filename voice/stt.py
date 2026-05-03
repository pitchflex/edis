# Speech-to-text — faster-whisper, records until silence

import logging
import tempfile
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd

import settings
from core.interrupt import check as interrupt_check

log = logging.getLogger(__name__)

_model = None


def _get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        log.info(f"Loading Whisper {settings.WHISPER_MODEL}...")
        _model = WhisperModel(
            settings.WHISPER_MODEL,
            device=settings.WHISPER_DEVICE,
            compute_type="int8",
        )
        log.info("Whisper ready")
    return _model


def record_until_silence() -> np.ndarray:
    """Record audio from mic until silence detected. Returns float32 numpy array."""
    sample_rate = settings.AUDIO_SAMPLE_RATE
    silence_threshold = settings.SILENCE_THRESHOLD
    silence_duration = settings.SILENCE_DURATION
    chunk = settings.AUDIO_CHUNK_SIZE

    frames = []
    silent_chunks = 0
    silent_chunks_needed = int(silence_duration * sample_rate / chunk)
    min_recording_chunks = int(0.5 * sample_rate / chunk)  # at least 0.5s

    with sd.InputStream(samplerate=sample_rate, channels=1,
                        dtype="float32", blocksize=chunk) as stream:
        log.debug("Recording...")
        while True:
            interrupt_check()
            data, _ = stream.read(chunk)
            frames.append(data.copy())
            rms = float(np.sqrt(np.mean(data ** 2)))
            if rms < silence_threshold:
                silent_chunks += 1
            else:
                silent_chunks = 0
            if len(frames) > min_recording_chunks and silent_chunks >= silent_chunks_needed:
                break

    audio = np.concatenate(frames, axis=0).flatten()
    return audio


def transcribe(audio: np.ndarray = None) -> str:
    """Transcribe audio. Records from mic if audio not provided."""
    if audio is None:
        audio = record_until_silence()

    model = _get_model()
    segments, _ = model.transcribe(
        audio,
        language="en",
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
    )
    text = " ".join(s.text for s in segments).strip()
    log.info(f"Transcribed: {text!r}")
    return text


def preload():
    """Preload model at startup so first use is instant."""
    _get_model()
