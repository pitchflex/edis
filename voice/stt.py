# Speech-to-text — Groq Whisper API (primary), local faster-whisper (fallback)
# Audio is recorded locally, sent to Groq for transcription. Uses key rotation.

import io
import logging
import wave

import numpy as np
import sounddevice as sd

import settings
from core import key_rotator as kr
from core.interrupt import check as interrupt_check

log = logging.getLogger(__name__)

GROQ_STT_MODEL = "whisper-large-v3-turbo"   # fast + accurate, free on Groq

# local fallback model (only loaded if Groq fails)
_local_model = None


# ── Recording ─────────────────────────────────────────────────────────────────

def record_until_silence() -> np.ndarray:
    """Record from mic until silence. Returns float32 numpy array at 16kHz."""
    sample_rate  = settings.AUDIO_SAMPLE_RATE
    chunk        = settings.AUDIO_CHUNK_SIZE
    sil_thresh   = settings.SILENCE_THRESHOLD
    sil_duration = settings.SILENCE_DURATION

    frames = []
    silent_chunks     = 0
    silent_needed     = int(sil_duration * sample_rate / chunk)
    min_chunks        = int(0.5 * sample_rate / chunk)  # at least 0.5s of audio

    with sd.InputStream(samplerate=sample_rate, channels=1,
                        dtype="float32", blocksize=chunk) as stream:
        log.debug("Recording...")
        while True:
            interrupt_check()
            data, _ = stream.read(chunk)
            frames.append(data.copy())
            rms = float(np.sqrt(np.mean(data ** 2)))
            silent_chunks = silent_chunks + 1 if rms < sil_thresh else 0
            if len(frames) > min_chunks and silent_chunks >= silent_needed:
                break

    return np.concatenate(frames, axis=0).flatten()


def _audio_to_wav_bytes(audio: np.ndarray) -> bytes:
    """Convert float32 numpy array to WAV bytes for API upload."""
    pcm = (audio * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)                    # 16-bit
        wf.setframerate(settings.AUDIO_SAMPLE_RATE)
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()


# ── Groq transcription ────────────────────────────────────────────────────────

def _transcribe_groq(audio: np.ndarray) -> str:
    import groq as groq_lib
    wav_bytes = _audio_to_wav_bytes(audio)
    last_err = None

    rotator = kr._rotators.get("groq")
    attempts = rotator.total_count() if rotator else 1

    for _ in range(attempts):
        key = kr.get("groq")
        if not key:
            raise RuntimeError("All Groq keys exhausted for STT")
        try:
            client = groq_lib.Groq(api_key=key)
            result = client.audio.transcriptions.create(
                file=("audio.wav", wav_bytes),
                model=GROQ_STT_MODEL,
                language="en",
                response_format="text",
            )
            kr.mark_ok("groq", key)
            text = result.strip() if isinstance(result, str) else result.text.strip()
            log.info(f"Groq STT: {text!r}")
            return text
        except groq_lib.RateLimitError as e:
            kr.mark_failed("groq", key, "STT rate limit")
            last_err = e
        except groq_lib.AuthenticationError as e:
            kr.mark_failed("groq", key, "STT auth error")
            last_err = e
        except Exception as e:
            last_err = e
            break

    raise last_err or RuntimeError("Groq STT failed")


# ── Local fallback ────────────────────────────────────────────────────────────

def _get_local_model():
    global _local_model
    if _local_model is None:
        from faster_whisper import WhisperModel
        log.info(f"Loading local Whisper {settings.WHISPER_MODEL} (fallback)...")
        _local_model = WhisperModel(
            settings.WHISPER_MODEL,
            device=settings.WHISPER_DEVICE,
            compute_type="int8",
        )
        log.info("Local Whisper ready")
    return _local_model


def _transcribe_local(audio: np.ndarray) -> str:
    model = _get_local_model()
    segments, _ = model.transcribe(
        audio,
        language="en",
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
    )
    text = " ".join(s.text for s in segments).strip()
    log.info(f"Local Whisper: {text!r}")
    return text


# ── Public API ────────────────────────────────────────────────────────────────

def transcribe(audio: np.ndarray = None) -> str:
    """Record (if needed) then transcribe via Groq API, falling back to local."""
    if audio is None:
        audio = record_until_silence()

    if not audio.any():
        return ""

    # try Groq first
    if kr._rotators.get("groq") and kr._rotators["groq"].available_count() > 0:
        try:
            return _transcribe_groq(audio)
        except Exception as e:
            log.warning(f"Groq STT failed, falling back to local: {e}")

    # local fallback
    return _transcribe_local(audio)


def preload():
    """No-op — Groq needs no preload. Kept for API compatibility."""
    log.debug("STT using Groq API — no preload needed")
