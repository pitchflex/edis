# Focus monitor — random screen check-ins during focus sessions

import logging
import random
import subprocess
import threading
import time
from pathlib import Path

import settings
from core.llm import get_llm

log = logging.getLogger(__name__)

VISION_PROMPT = """The user said they are {activity}. Look at this screenshot.
Are they focused on that activity, or distracted by something unrelated?
Reply in this exact JSON format:
{{"focused": true/false, "what_doing": "brief description", "distraction": "name if distracted else null"}}
Be brief and accurate. Only JSON, no explanation."""

ALERT_MESSAGES = {
    "gentle": "Looks like you drifted to {distraction}, {name}. Getting back on track?",
    "firm":   "{name}, you're on {distraction}. Back to {activity}.",
    "strict": "Focus alert — {distraction} detected. Return to {activity} immediately, {name}.",
}


class FocusSession:
    def __init__(self, activity: str, duration_minutes: int, on_alert):
        self.activity = activity
        self.duration_minutes = duration_minutes
        self.on_alert = on_alert
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self.start_time = time.time()
        self.distractions: list[dict] = []
        self.checks_done = 0

    def start(self):
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        log.info(f"Focus monitor started — {self.activity} for {self.duration_minutes}min")

    def stop(self):
        self._stop_event.set()
        log.info("Focus monitor stopped")

    def summary(self) -> str:
        elapsed = int((time.time() - self.start_time) / 60)
        n = len(self.distractions)
        if n == 0:
            return f"You stayed focused the entire {elapsed} minutes. Excellent work."
        names = ", ".join(d["distraction"] for d in self.distractions if d.get("distraction"))
        return (f"Session complete — {elapsed} minutes. "
                f"Drifted {n} time{'s' if n != 1 else ''} ({names}).")

    def _monitor_loop(self):
        end_time = self.start_time + self.duration_minutes * 60
        while not self._stop_event.is_set() and time.time() < end_time:
            wait = random.uniform(
                settings.FOCUS_CHECK_MIN_MINS * 60,
                settings.FOCUS_CHECK_MAX_MINS * 60
            )
            # sleep in small increments so we can be interrupted
            for _ in range(int(wait)):
                if self._stop_event.is_set():
                    return
                time.sleep(1)

            if self._stop_event.is_set():
                return

            self._do_check()

        if not self._stop_event.is_set():
            # session ended naturally
            self.on_alert(self.summary(), is_summary=True)

    def _do_check(self):
        self.checks_done += 1
        screenshot_path = settings.SCREENSHOT_TMP
        try:
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["grim", str(screenshot_path)],
                check=True, capture_output=True, timeout=5
            )
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
            log.warning(f"Screenshot failed: {e}")
            return

        try:
            llm = get_llm()
            import json
            prompt = VISION_PROMPT.format(activity=self.activity)
            result_text = llm.vision(str(screenshot_path), prompt)
            result_text = result_text.strip()
            if result_text.startswith("```"):
                result_text = result_text.split("\n", 1)[1].rsplit("```", 1)[0]
            result = json.loads(result_text)

            if not result.get("focused", True):
                distraction = result.get("distraction", "something else")
                self.distractions.append(result)
                if settings.PRIVACY_LOG_DISTRACTIONS:
                    from memory.manager import get_memory
                    get_memory().remember(
                        "episode",
                        f"Distracted by {distraction} during {self.activity}",
                        key="distraction_event"
                    )
                template = ALERT_MESSAGES.get(settings.FOCUS_ALERT_TONE, ALERT_MESSAGES["gentle"])
                msg = template.format(
                    distraction=distraction,
                    activity=self.activity,
                    name=settings.EDIS_USER_NAME,
                )
                self.on_alert(msg, is_summary=False)
        except Exception as e:
            log.debug(f"Focus check analysis failed: {e}")
        finally:
            if settings.FOCUS_DELETE_SCREENSHOT and screenshot_path.exists():
                screenshot_path.unlink()


_active_session: FocusSession | None = None


def start_session(activity: str, duration_minutes: int, on_alert) -> FocusSession:
    global _active_session
    if _active_session:
        _active_session.stop()
    _active_session = FocusSession(activity, duration_minutes, on_alert)
    _active_session.start()
    return _active_session


def stop_session():
    global _active_session
    if _active_session:
        _active_session.stop()
        _active_session = None


def get_active() -> FocusSession | None:
    return _active_session
