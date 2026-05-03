# Text-to-speech — Piper TTS (local, free)
# Falls back to espeak if Piper not installed.

import logging
import subprocess
import threading
from pathlib import Path

import settings

log = logging.getLogger(__name__)

_current_process: subprocess.Popen | None = None
_lock = threading.Lock()


def speak(text: str):
    """Speak text aloud. Stops any currently playing speech first."""
    stop()
    text = text.strip()
    if not text:
        return
    log.debug(f"Speaking: {text!r}")

    piper_model = _find_piper_model()
    if piper_model:
        _speak_piper(text, piper_model)
    else:
        _speak_espeak(text)


def stop():
    """Immediately stop current speech."""
    global _current_process
    with _lock:
        if _current_process and _current_process.poll() is None:
            _current_process.terminate()
            _current_process = None


def _find_piper_model() -> Path | None:
    voice = settings.TTS_VOICE
    piper_dir = settings.PIPER_DIR
    # check common locations
    candidates = [
        piper_dir / f"{voice}.onnx",
        Path.home() / ".local" / "share" / "piper" / f"{voice}.onnx",
        Path(f"/usr/share/piper-voices/{voice}.onnx"),
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def _speak_piper(text: str, model_path: Path):
    global _current_process
    cmd = [
        "piper",
        "--model", str(model_path),
        "--output-raw",
    ]
    play_cmd = ["aplay", "-r", "22050", "-f", "S16_LE", "-c", "1", "-t", "raw", "-"]
    try:
        piper_proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
        )
        play_proc = subprocess.Popen(
            play_cmd, stdin=piper_proc.stdout,
            stderr=subprocess.DEVNULL
        )
        piper_proc.stdin.write(text.encode())
        piper_proc.stdin.close()
        with _lock:
            _current_process = play_proc
        play_proc.wait()
    except FileNotFoundError:
        log.warning("Piper not found, falling back to espeak")
        _speak_espeak(text)


def _speak_espeak(text: str):
    global _current_process
    try:
        proc = subprocess.Popen(
            ["espeak-ng", "-s", "160", "-p", "50", text],
            stderr=subprocess.DEVNULL
        )
        with _lock:
            _current_process = proc
        proc.wait()
    except FileNotFoundError:
        log.error("No TTS available — install piper or espeak-ng")


def install_voice_instructions() -> str:
    voice = settings.TTS_VOICE
    return f"""Piper voice not found. To install:
1. Download: https://github.com/rhasspy/piper/releases
2. Get model: {voice}.onnx from https://huggingface.co/rhasspy/piper-voices
3. Place in: {settings.PIPER_DIR}/
4. Install piper binary: sudo dnf install piper (or download from GitHub)"""
