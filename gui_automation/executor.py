# Action executor — ydotool for mouse/keyboard on Wayland

import logging
import subprocess
import time

import settings

log = logging.getLogger(__name__)


def _ydotool(*args) -> bool:
    try:
        result = subprocess.run(["ydotool", *args], capture_output=True, timeout=5)
        return result.returncode == 0
    except FileNotFoundError:
        log.error("ydotool not found. Install: sudo dnf install ydotool")
        return False
    except subprocess.TimeoutExpired:
        return False


def click(x: int, y: int, button: int = 1):
    _ydotool("mousemove", "--absolute", f"--xpos={x}", f"--ypos={y}")
    time.sleep(0.05)
    _ydotool("click", f"0x{button:02X}0")
    time.sleep(settings.GUI_ACTION_DELAY_MS / 1000)


def right_click(x: int, y: int):
    click(x, y, button=3)


def double_click(x: int, y: int):
    _ydotool("mousemove", "--absolute", f"--xpos={x}", f"--ypos={y}")
    time.sleep(0.05)
    _ydotool("click", "--repeat=2", "--delay=100", "0x00")
    time.sleep(settings.GUI_ACTION_DELAY_MS / 1000)


def type_text(text: str):
    _ydotool("type", "--delay=50", "--", text)
    time.sleep(settings.GUI_ACTION_DELAY_MS / 1000)


def press_key(key: str):
    # key in xdotool format: "Return", "ctrl+c", "super+d", etc.
    _ydotool("key", "--", key)
    time.sleep(settings.GUI_ACTION_DELAY_MS / 1000)


def scroll(x: int, y: int, direction: str = "down", amount: int = 3):
    _ydotool("mousemove", "--absolute", f"--xpos={x}", f"--ypos={y}")
    button = "5" if direction == "down" else "4"
    for _ in range(amount):
        _ydotool("click", f"0x{int(button):02X}0")


def move_mouse(x: int, y: int):
    _ydotool("mousemove", "--absolute", f"--xpos={x}", f"--ypos={y}")


def execute_action(action: dict) -> bool:
    """Execute a single automation action dict from the vision loop."""
    from core.interrupt import check as interrupt_check
    interrupt_check()

    t = action.get("type")
    if t == "click":
        click(action["x"], action["y"])
    elif t == "right_click":
        right_click(action["x"], action["y"])
    elif t == "double_click":
        double_click(action["x"], action["y"])
    elif t == "type":
        type_text(action["text"])
    elif t == "key":
        press_key(action["key"])
    elif t == "scroll":
        scroll(action.get("x", 960), action.get("y", 540),
               action.get("direction", "down"), action.get("amount", 3))
    elif t == "wait":
        time.sleep(action.get("seconds", 1))
    elif t == "done":
        return False  # signal loop to stop
    else:
        log.warning(f"Unknown action type: {t}")
    return True
