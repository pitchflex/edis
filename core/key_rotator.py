# API key rotation — round-robin with automatic cooldown on rate limits.
# Every API-dependent module uses this instead of reading keys directly.

import logging
import time
from threading import Lock

log = logging.getLogger(__name__)

# How long (seconds) before retrying a rate-limited key
KEY_COOLDOWN = 65


class KeyRotator:
    """
    Holds a list of API keys for one provider and rotates through them.
    On rate limit / auth error, marks the current key as failed and
    moves to the next. Keys automatically recover after KEY_COOLDOWN seconds.
    """

    def __init__(self, provider: str, keys: list[str]):
        self._provider = provider
        self._keys = [k.strip() for k in keys if k and k.strip()]
        self._index = 0
        self._failed: dict[str, float] = {}   # key -> time it was marked failed
        self._lock = Lock()

    def get(self) -> str | None:
        """Return the next available key, or None if all are exhausted."""
        with self._lock:
            now = time.time()
            for _ in range(len(self._keys)):
                key = self._keys[self._index]
                self._index = (self._index + 1) % len(self._keys)
                failed_at = self._failed.get(key, 0)
                if now - failed_at >= KEY_COOLDOWN:
                    return key
            log.error(f"[{self._provider}] All {len(self._keys)} keys are rate-limited. "
                      f"Retry in {KEY_COOLDOWN}s.")
            return None

    def mark_failed(self, key: str, reason: str = "rate limit"):
        with self._lock:
            self._failed[key] = time.time()
            remaining = sum(
                1 for k in self._keys
                if time.time() - self._failed.get(k, 0) >= KEY_COOLDOWN
            )
            log.warning(f"[{self._provider}] Key ...{key[-6:]} marked failed ({reason}). "
                        f"{remaining}/{len(self._keys)} keys still available.")

    def mark_ok(self, key: str):
        with self._lock:
            self._failed.pop(key, None)

    def available_count(self) -> int:
        now = time.time()
        return sum(
            1 for k in self._keys
            if now - self._failed.get(k, 0) >= KEY_COOLDOWN
        )

    def total_count(self) -> int:
        return len(self._keys)

    def has_any(self) -> bool:
        return bool(self._keys)

    def status(self) -> str:
        return f"{self._provider}: {self.available_count()}/{self.total_count()} keys available"


# ── Global rotators — one per provider ───────────────────────────────────────
# Populated at startup by init_rotators()

_rotators: dict[str, KeyRotator] = {}


def init_rotators():
    """Build rotators from settings. Call once at startup."""
    import settings

    def _to_list(single_key: str, multi_key_attr: str) -> list[str]:
        # supports both groq_key = "x" and groq_keys = ["x","y"]
        multi = getattr(settings, multi_key_attr, [])
        if isinstance(multi, list) and multi:
            return multi
        single = single_key.strip() if single_key else ""
        return [single] if single else []

    _rotators["groq"]       = KeyRotator("groq",       _to_list(settings.GROQ_API_KEY,       "GROQ_API_KEYS"))
    _rotators["gemini"]     = KeyRotator("gemini",     _to_list(settings.GEMINI_API_KEY,     "GEMINI_API_KEYS"))
    _rotators["elevenlabs"] = KeyRotator("elevenlabs", _to_list(settings.ELEVENLABS_API_KEY, "ELEVENLABS_API_KEYS"))
    _rotators["openweather"]= KeyRotator("openweather",_to_list(settings.OPENWEATHER_KEY,    "OPENWEATHER_KEYS"))

    for r in _rotators.values():
        if r.has_any():
            log.info(r.status())


def get(provider: str) -> str | None:
    """Get the next available key for a provider."""
    r = _rotators.get(provider)
    if not r:
        return None
    return r.get()


def mark_failed(provider: str, key: str, reason: str = "rate limit"):
    r = _rotators.get(provider)
    if r:
        r.mark_failed(key, reason)


def mark_ok(provider: str, key: str):
    r = _rotators.get(provider)
    if r:
        r.mark_ok(key)


def status_all() -> list[str]:
    return [r.status() for r in _rotators.values() if r.has_any()]
