# Wake word detection — openwakeword v0.4.0, runs in background thread

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
        from openwakeword.model import Model
        import pathlib, openwakeword

        oww_dir = pathlib.Path(openwakeword.__file__).parent

        # use custom model if trained, otherwise fall back to hey_jarvis
        custom = settings.BASE_DIR / "wake_word" / "edis.onnx"
        if custom.exists():
            model_path = str(custom)
            log.info("Using custom EDIS wake word model")
        else:
            model_path = str(oww_dir / "resources" / "models" / "hey_jarvis_v0.1.onnx")
            log.warning(
                f"Custom wake word not found at {custom}. "
                "Using 'hey_jarvis' as stand-in — say 'hey jarvis' to activate. "
                f"Train a custom model and place at {custom} for 'edis' wake word."
            )

        oww = Model(wakeword_model_paths=[model_path], vad_threshold=0.5)

        chunk = 1280  # 80ms at 16kHz
        with sd.InputStream(samplerate=16000, channels=1,
                            dtype="int16", blocksize=chunk) as stream:
            while _running:
                data, _ = stream.read(chunk)
                audio = data.flatten().astype(np.int16)
                oww.predict(audio)

                for name, scores in oww.prediction_buffer.items():
                    score = scores[-1] if len(scores) else 0
                    if score >= settings.WAKE_SENSITIVITY:
                        log.info(f"Wake word detected (model={name}, score={score:.2f})")
                        # reset buffer to avoid re-triggering
                        for k in oww.prediction_buffer:
                            oww.prediction_buffer[k] = [0.0] * len(oww.prediction_buffer[k])
                        on_detected()
                        break

    except ImportError:
        log.error("openwakeword not installed. Run: pip install openwakeword")
    except Exception as e:
        log.error(f"Wake word listener crashed: {e}")
