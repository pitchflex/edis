# D-Bus service — communication bridge between Python backend and GNOME Shell extension

import logging
import threading
from typing import Callable

import settings

log = logging.getLogger(__name__)

DBUS_INTROSPECT_XML = f"""
<node>
  <interface name='{settings.DBUS_SERVICE_NAME}'>
    <method name='SetState'>
      <arg type='s' name='state' direction='in'/>
    </method>
    <method name='AddLog'>
      <arg type='s' name='role' direction='in'/>
      <arg type='s' name='text' direction='in'/>
    </method>
    <method name='GetState'>
      <arg type='s' name='state' direction='out'/>
    </method>
    <signal name='StateChanged'>
      <arg type='s' name='state'/>
    </signal>
    <signal name='NewLogEntry'>
      <arg type='s' name='role'/>
      <arg type='s' name='text'/>
    </signal>
    <signal name='InterruptRequested'/>
  </interface>
</node>
"""

UI_STATES = {
    "idle":       "IDLE",
    "standby":    "STANDBY",
    "listening":  "LISTENING",
    "thinking":   "THINKING",
    "responding": "RESPONDING",
    "working":    "WORKING",
}


class EdisDBusService:
    def __init__(self, on_interrupt: Callable = None):
        self._state = "standby"
        self._on_interrupt = on_interrupt or (lambda: None)
        self._bus = None
        self._obj = None

    def start(self):
        try:
            from pydbus import SessionBus
            from gi.repository import GLib

            bus = SessionBus()
            bus.publish(settings.DBUS_SERVICE_NAME, self)
            self._bus = bus
            log.info(f"D-Bus service published: {settings.DBUS_SERVICE_NAME}")
        except ImportError:
            log.warning("pydbus not installed — UI extension won't connect. pip install pydbus")
        except Exception as e:
            log.warning(f"D-Bus service failed to start: {e}")

    def SetState(self, state: str):
        self._state = state
        try:
            self.StateChanged(state)
        except Exception:
            pass

    def AddLog(self, role: str, text: str):
        try:
            self.NewLogEntry(role, text)
        except Exception:
            pass

    def GetState(self) -> str:
        return self._state

    # signals (emitted by calling them)
    StateChanged = ("StateChanged", "s")
    NewLogEntry = ("NewLogEntry", "ss")
    InterruptRequested = ("InterruptRequested", "")


_service: EdisDBusService | None = None


def get_service() -> EdisDBusService | None:
    return _service


def init(on_interrupt: Callable = None) -> EdisDBusService:
    global _service
    _service = EdisDBusService(on_interrupt=on_interrupt)
    return _service


def set_state(state: str):
    if _service:
        _service.SetState(state)


def add_log(role: str, text: str):
    if _service:
        _service.AddLog(role, text)
