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


class EdisDBusService:
    # pydbus reads this attribute for introspection
    dbus = DBUS_INTROSPECT_XML

    def __init__(self, on_interrupt: Callable = None):
        self._state = "standby"
        self._on_interrupt = on_interrupt or (lambda: None)

    # ── D-Bus methods ─────────────────────────────────────────────────────────

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

    def TriggerInterrupt(self):
        self._on_interrupt()

    # ── Signals — defined via pydbus.generic.signal ───────────────────────────


def _make_service(on_interrupt):
    """Build service with pydbus signals attached."""
    try:
        from pydbus.generic import signal as dbus_signal

        class _Service(EdisDBusService):
            StateChanged      = dbus_signal()
            NewLogEntry       = dbus_signal()
            InterruptRequested= dbus_signal()

        return _Service(on_interrupt=on_interrupt)
    except ImportError:
        return EdisDBusService(on_interrupt=on_interrupt)


_service: EdisDBusService | None = None
_bus = None


def get_service() -> EdisDBusService | None:
    return _service


def init(on_interrupt: Callable = None) -> EdisDBusService:
    global _service
    _service = _make_service(on_interrupt)
    return _service


def start():
    global _bus
    if _service is None:
        return
    try:
        from pydbus import SessionBus
        _bus = SessionBus()
        _bus.publish(settings.DBUS_SERVICE_NAME, _service)
        log.info(f"D-Bus service published: {settings.DBUS_SERVICE_NAME}")
    except ImportError:
        log.warning("pydbus not installed — extension UI won't connect. pip install pydbus")
    except Exception as e:
        log.warning(f"D-Bus service failed to start: {e}")


def set_state(state: str):
    if _service:
        try:
            _service.SetState(state)
        except Exception:
            pass


def add_log(role: str, text: str):
    if _service:
        try:
            _service.AddLog(role, text)
        except Exception:
            pass
