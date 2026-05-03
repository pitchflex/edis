#!/usr/bin/env python3
# EDIS — Enhanced Digital Intelligence System
# Entry point: starts all services and the main voice loop

import logging
import os
import subprocess
import sys
import threading

import settings
from core import dbus_service, engine, interrupt
from proactivity import engine as proactivity
from voice import stt, tts, wake_word

# ── Logging ───────────────────────────────────────────────────────────────────

settings.LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
settings.BASE_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(settings.LOG_FILE),
    ]
)
log = logging.getLogger("edis.main")

# ── State machine ─────────────────────────────────────────────────────────────

_state = "standby"
_listen_event = threading.Event()
_state_lock = threading.Lock()


def set_state(state: str):
    global _state
    with _state_lock:
        _state = state
    dbus_service.set_state(state)
    log.debug(f"State → {state}")


# ── UI helpers ────────────────────────────────────────────────────────────────

def on_ui_update(role: str, text: str):
    dbus_service.add_log(role, text)
    if role == "tool":
        log.debug(f"[tool] {text}")
    else:
        log.info(f"[{role}] {text}")


def on_speak(text: str):
    tts.speak(text)


# ── Wake word / hotkey callback ───────────────────────────────────────────────

def on_wake():
    """Called when wake word detected or hotkey pressed."""
    interrupt.interrupt()   # stop anything running
    interrupt.clear()
    _listen_event.set()


# ── Main voice loop ───────────────────────────────────────────────────────────

def voice_loop():
    log.info("Voice loop started")
    while True:
        _listen_event.wait()
        _listen_event.clear()

        if interrupt.is_set():
            interrupt.clear()

        set_state("listening")
        try:
            user_input = stt.transcribe()
        except InterruptedError:
            set_state("standby")
            continue
        except Exception as e:
            log.error(f"STT error: {e}")
            set_state("standby")
            continue

        if not user_input.strip():
            set_state("standby")
            continue

        set_state("thinking")

        # check proactivity for situation-based suggestions
        eng = engine.get_engine()
        pe = proactivity.get_engine()
        suggestion = pe.on_user_message(user_input) if pe else None

        if suggestion and suggestion["action"] in ("ask", "offer"):
            set_state("responding")
            msg = suggestion["message"]
            on_ui_update("edis", msg)
            on_speak(msg)

            # listen for user's response to the suggestion
            set_state("listening")
            try:
                followup = stt.transcribe()
                accepted = _is_affirmative(followup)
                # always extract actions — needed when user accepts an "ask"
                # e.g. "play lofi and mute notifications" → stored as preference
                actions = _extract_actions(followup)

                pe.on_preference_response(followup, accepted, actions=actions or None)

                if accepted:
                    # confirmed — acknowledge and execute the original request
                    response = eng.process(user_input)
                else:
                    # declined — still process original but skip preference actions
                    response = eng.process(user_input)
            except Exception as e:
                log.error(f"Followup error: {e}")
                response = eng.process(user_input)
        else:
            try:
                # set working state if likely a task
                set_state("thinking")
                response = eng.process(user_input)
            except InterruptedError:
                set_state("standby")
                continue
            except Exception as e:
                log.error(f"Engine error: {e}")
                response = f"I encountered an error, {settings.EDIS_USER_NAME}."
                on_ui_update("edis", response)

        set_state("responding")
        on_speak(response)
        set_state("standby")


def _is_affirmative(text: str) -> bool:
    t = text.lower().strip()
    return any(w in t for w in ("yes", "yeah", "sure", "ok", "okay",
                                "please", "do it", "go ahead", "yep"))


def _extract_actions(text: str) -> list:
    """Extract a simple list of actions from user's natural language response."""
    try:
        from core.llm import get_llm
        import json
        llm = get_llm()
        response = llm.chat([{
            "role": "user",
            "content": f"""Extract the list of actions from this text as a JSON array of short strings.
Text: "{text}"
Example: ["play lofi music", "mute notifications", "set brightness to 50%"]
Return only JSON array."""
        }])
        text_clean = response.strip()
        if text_clean.startswith("```"):
            text_clean = text_clean.split("\n", 1)[1].rsplit("```", 1)[0]
        return json.loads(text_clean)
    except Exception:
        return [text.strip()]


# ── Startup ───────────────────────────────────────────────────────────────────

def startup():
    # ensure required dirs
    for d in [settings.MEMORY_DIR, settings.SKILLS_DIR,
              settings.PIPER_DIR, settings.SCREENSHOT_TMP.parent]:
        d.mkdir(parents=True, exist_ok=True)

    # init key rotators before anything else touches the APIs
    from core.key_rotator import init_rotators, status_all
    init_rotators()
    for s in status_all():
        log.info(f"Keys: {s}")

    # check critical dependencies
    _check_deps()

    # init D-Bus service
    dbus_service.init(on_interrupt=on_wake)
    dbus_service.start()

    # init core engine
    engine.init(on_speak=on_speak, on_ui_update=on_ui_update)

    # init proactivity engine
    pe = proactivity.init(on_speak=on_speak, on_ui=lambda msg: on_ui_update("edis", msg))
    pe.start()

    # start Obsidian memory sync
    from memory.obsidian_sync import start_background_sync
    start_background_sync()

    # preload whisper model in background
    threading.Thread(target=stt.preload, daemon=True).start()

    # start wake word listener
    wake_word.start(on_detected=on_wake)

    # startup sound + greeting
    if settings.EDIS_STARTUP_SOUND:
        _play_startup_sound()

    greeting = (
        f"{settings.ASSISTANT_NAME} online. All systems nominal. "
        f"Good {_time_of_day()}, {settings.EDIS_USER_NAME}."
    )
    log.info(greeting)
    on_ui_update("edis", greeting)
    threading.Thread(target=lambda: tts.speak(greeting), daemon=True).start()

    log.info(f"EDIS {settings.VERSION} ready — say '{settings.WAKE_WORD}' or press {settings.HOTKEY}")


def _play_startup_sound():
    sounds = [
        "/usr/share/sounds/freedesktop/stereo/service-login.oga",
        "/usr/share/sounds/freedesktop/stereo/bell.oga",
    ]
    for s in sounds:
        if os.path.exists(s):
            subprocess.Popen(["paplay", s], stderr=subprocess.DEVNULL)
            return


def _time_of_day() -> str:
    from datetime import datetime
    h = datetime.now().hour
    if h < 12:
        return "morning"
    if h < 17:
        return "afternoon"
    return "evening"


def _check_deps():
    missing = []
    bins = ["grim", "ydotool", "pactl", "notify-send", "gio"]
    for b in bins:
        if subprocess.run(["which", b], capture_output=True).returncode != 0:
            missing.append(b)
    if missing:
        log.warning(f"Missing system tools: {', '.join(missing)} — some features may not work")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        startup()
        voice_loop()
    except KeyboardInterrupt:
        log.info("EDIS shutting down")
        tts.stop()
        wake_word.stop()
        sys.exit(0)
