# Global interrupt handler — highest priority in the system.
# Any component can call interrupt() to immediately stop everything.

import threading
import logging

log = logging.getLogger(__name__)

_interrupt_event = threading.Event()
_listeners: list = []
_lock = threading.Lock()


def register(callback):
    """Register a callback to be called on interrupt."""
    with _lock:
        _listeners.append(callback)


def unregister(callback):
    with _lock:
        _listeners.discard(callback) if hasattr(_listeners, 'discard') else None
        try:
            _listeners.remove(callback)
        except ValueError:
            pass


def interrupt():
    """Fire the global interrupt — stops all running tasks immediately."""
    log.info("Interrupt fired")
    _interrupt_event.set()
    with _lock:
        callbacks = list(_listeners)
    for cb in callbacks:
        try:
            cb()
        except Exception as e:
            log.error(f"Interrupt callback error: {e}")


def clear():
    """Clear the interrupt flag after handling."""
    _interrupt_event.clear()


def is_set() -> bool:
    return _interrupt_event.is_set()


def check():
    """Raise InterruptedError if interrupted — call this in long-running loops."""
    if _interrupt_event.is_set():
        raise InterruptedError("EDIS interrupt received")


class InterruptibleTask:
    """Context manager for tasks that should be cancellable."""

    def __init__(self, name: str):
        self.name = name
        self._cancelled = False
        register(self._on_interrupt)

    def _on_interrupt(self):
        self._cancelled = True
        log.debug(f"Task '{self.name}' received interrupt")

    def check(self):
        if self._cancelled or is_set():
            raise InterruptedError(f"Task '{self.name}' interrupted")

    def __enter__(self):
        self._cancelled = False
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        unregister(self._on_interrupt)
        return False
