# Wake word detection — openwakeword, runs in background thread
# Fires callback when "edis" (or configured word) is detected.

import logging
import threading
from typing import Callable

import numpy as np
import sounddevice as sd

import settings

log = logging.getLogger(__name__)

_running = False
_thread: threading.Thread | None = None


def start(on_detected: Callable):
    """Start wake word detection in background thread."""
    global _running, _thread
    _running = True
    _thread = threading.Thread(target=_listen_loop, args=(on_detected,), daemon=True)
    _thread.start()
    log.info(f"Wake word listener started — say '{settings.WAKE_WORD}'")


def stop():
    global _running
    _running = False


def _listen_loop(on_detected: Callable):
    try:
        import openwakeword
        from openwakeword.model import Model

        # openwakeword comes with "hey_jarvis" and other models.
        # For "edis" we use the closest available or a custom trained model.
        # Custom model path: ~/.edis/wake_word/edis.onnx
        custom = settings.BASE_DIR / "wake_word" / "edis.onnx"
        if custom.exists():
            oww = Model(wakeword_models=[str(custom)], inference_framework="onnx")
            log.info("Using custom EDIS wake word model")
        else:
            oww = Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")
            log.warning(
                "Custom wake word model not found — using 'hey_jarvis' as placeholder. "
                f"Train a custom model and place at {custom}"
            )

        chunk = 1280  # 80ms at 16kHz — openwakeword requirement
        with sd.InputStream(samplerate=16000, channels=1,
                            dtype="int16", blocksize=chunk) as stream:
            while _running:
                data, _ = stream.read(chunk)
                audio = data.flatten().astype(np.int16)
                oww.predict(audio)
                for name, score in oww.prediction_buffer.items():
                    latest = score[-1] if score else 0
                    if latest >= settings.WAKE_SENSITIVITY:
                        log.info(f"Wake word detected (score={latest:.2f})")
                        oww.reset()
                        on_detected()
                        break

    except ImportError:
        log.error("openwakeword not installed. Wake word disabled. Run: pip install openwakeword")
    except Exception as e:
        log.error(f"Wake word listener crashed: {e}")
