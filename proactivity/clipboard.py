# Clipboard intelligence — watches clipboard and offers relevant actions

import json
import logging
import threading
import time
from typing import Callable

import settings

log = logging.getLogger(__name__)

CLASSIFY_PROMPT = """Look at this clipboard content and identify what it is.
Return JSON: {{"type": "tracking_number"|"address"|"phone_number"|"email"|"url"|"code_error"|"code"|"unknown", "suggestion": "short action to offer (under 15 words)", "offer": true/false}}
Only offer (offer=true) if there's a clearly useful action. Be conservative.
Content: {content}"""

_running = False
_last_content = ""
_thread: threading.Thread | None = None


def start(on_suggestion: Callable[[str, str], None]):
    """Start clipboard watcher. on_suggestion(suggestion_text, content) called when relevant."""
    global _running, _thread
    if not settings.CLIPBOARD_WATCH:
        return
    _running = True
    _thread = threading.Thread(target=_watch_loop, args=(on_suggestion,), daemon=True)
    _thread.start()
    log.info("Clipboard watcher started")


def stop():
    global _running
    _running = False


def _watch_loop(on_suggestion: Callable):
    global _last_content
    try:
        import pyperclip
    except ImportError:
        log.error("pyperclip not installed — clipboard watch disabled. pip install pyperclip")
        return

    while _running:
        try:
            content = pyperclip.paste()
            if content and content != _last_content and len(content) < 2000:
                _last_content = content
                if settings.CLIPBOARD_INTEL:
                    _analyze(content, on_suggestion)
        except Exception as e:
            log.debug(f"Clipboard read error: {e}")
        time.sleep(1.5)


def _analyze(content: str, on_suggestion: Callable):
    try:
        from core.llm import get_llm
        llm = get_llm()
        response = llm.chat([{
            "role": "user",
            "content": CLASSIFY_PROMPT.format(content=content[:500])
        }])
        text = response.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0]
        result = json.loads(text)
        if result.get("offer") and result.get("suggestion"):
            log.debug(f"Clipboard suggestion: {result['suggestion']}")
            on_suggestion(result["suggestion"], content)
    except Exception as e:
        log.debug(f"Clipboard analysis skipped: {e}")
