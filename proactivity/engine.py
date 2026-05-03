# Proactivity engine — background monitors, DND, interrupt budget

import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Callable

import psutil

import settings
from proactivity import clipboard, focus_monitor
from proactivity.preferences import get_learner
from proactivity.situation import classify, is_focus_session

log = logging.getLogger(__name__)


class ProactivityEngine:
    def __init__(self, on_speak: Callable[[str], None], on_ui_message: Callable[[str], None]):
        self.on_speak = on_speak
        self.on_ui = on_ui_message
        self._interrupts_this_hour: list[datetime] = []
        self._running = False
        self._pending_preference: dict | None = None

    def start(self):
        self._running = True
        clipboard.start(self._on_clipboard_suggestion)
        threading.Thread(target=self._system_monitor_loop, daemon=True).start()
        log.info("Proactivity engine started")

    def stop(self):
        self._running = False
        clipboard.stop()
        focus_monitor.stop_session()

    # ── Called by engine when user speaks ─────────────────────────────────────

    def on_user_message(self, message: str) -> dict | None:
        """
        Analyze user message for situations that need proactive handling.
        Returns a proactive suggestion dict or None.
        """
        situation = classify(message)
        if situation["type"] == "unknown" or situation["confidence"] < 0.6:
            return None

        learner = get_learner()
        result = learner.handle_situation(
            context_type=situation["type"],
            activity=situation.get("activity") or situation["type"].replace("_", " "),
        )

        if result["action"] == "none":
            return None

        # store pending so we can handle the user's response
        self._pending_preference = {
            "situation": situation,
            "preference_result": result,
        }

        if is_focus_session(situation) and situation.get("duration_minutes"):
            self._pending_preference["start_focus"] = True

        return result

    def on_preference_response(self, user_response: str, accepted: bool,
                               actions: list = None):
        """Called after user responds to a preference offer/ask."""
        if not self._pending_preference:
            return

        pref = self._pending_preference
        context_type = pref["preference_result"]["context_type"]
        learner = get_learner()

        if pref["preference_result"]["action"] == "ask" and accepted and actions:
            learner.store_preference(context_type, actions)
        elif pref["preference_result"]["action"] == "offer":
            learner.record_outcome(context_type, accepted)

        if accepted and pref.get("start_focus"):
            sit = pref["situation"]
            self._start_focus_session(
                activity=sit.get("activity", "focusing"),
                duration=sit.get("duration_minutes", 60),
            )

        self._pending_preference = None

    def _start_focus_session(self, activity: str, duration: int):
        focus_monitor.start_session(
            activity=activity,
            duration_minutes=duration,
            on_alert=self._on_focus_alert,
        )

    def _on_focus_alert(self, message: str, is_summary: bool = False):
        if self._can_interrupt():
            self._notify(message)

    def _on_clipboard_suggestion(self, suggestion: str, content: str):
        if self._can_interrupt():
            msg = f"{settings.EDIS_USER_NAME}, {suggestion}"
            self._notify(msg)

    # ── System monitor ────────────────────────────────────────────────────────

    def _system_monitor_loop(self):
        while self._running:
            try:
                self._check_battery()
            except Exception as e:
                log.debug(f"System monitor error: {e}")
            time.sleep(30)

    def _check_battery(self):
        battery = psutil.sensors_battery()
        if battery and not battery.power_plugged:
            if battery.percent <= settings.PROACTIVE_BATTERY_ALERT:
                msg = (f"Battery at {int(battery.percent)}%, {settings.EDIS_USER_NAME}. "
                       "Consider plugging in.")
                if self._can_interrupt():
                    self._notify(msg)

    # ── DND + interrupt budget ─────────────────────────────────────────────────

    def _can_interrupt(self) -> bool:
        if not settings.PROACTIVE_ENABLED:
            return False
        if self._is_dnd():
            return False
        # trim old entries
        cutoff = datetime.now() - timedelta(hours=1)
        self._interrupts_this_hour = [t for t in self._interrupts_this_hour if t > cutoff]
        return len(self._interrupts_this_hour) < settings.PROACTIVE_INTERRUPT_MAX

    def _is_dnd(self) -> bool:
        now = datetime.now().strftime("%H:%M")
        start = settings.PROACTIVE_DND_START
        end = settings.PROACTIVE_DND_END
        if start <= end:
            return start <= now <= end
        return now >= start or now <= end  # overnight DND

    def _notify(self, message: str):
        self._interrupts_this_hour.append(datetime.now())
        self.on_speak(message)
        self.on_ui(message)


_engine: ProactivityEngine | None = None


def get_engine() -> ProactivityEngine | None:
    return _engine


def init(on_speak: Callable, on_ui: Callable) -> ProactivityEngine:
    global _engine
    _engine = ProactivityEngine(on_speak, on_ui)
    return _engine
