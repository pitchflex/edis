# settings.py — single source of truth for all EDIS configuration
# Every module does: import settings  then uses settings.SOME_VALUE

from pathlib import Path
import sys

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        raise ImportError("Install tomli: pip install tomli  (needed for Python < 3.11)")

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR       = Path.home() / ".edis"
CONFIG_FILE    = Path(__file__).parent / "config.toml"
SKILLS_DIR     = BASE_DIR / "skills"
MEMORY_DIR     = BASE_DIR / "memory"
MEMORY_DB      = MEMORY_DIR / "edis.db"
CHROMA_DIR     = MEMORY_DIR / "chroma"
LOG_FILE       = BASE_DIR / "logs" / "edis.log"
SCREENSHOT_TMP = BASE_DIR / "tmp" / "screen_check.png"
PIPER_DIR      = BASE_DIR / "piper"

# ── Load user config ──────────────────────────────────────────────────────────
_cfg: dict = {}
if CONFIG_FILE.exists():
    with open(CONFIG_FILE, "rb") as f:
        _cfg = tomllib.load(f)

def _get(section: str, key: str, default):
    return _cfg.get(section, {}).get(key, default)

# ── API Keys — single key or list of keys (rotation) ─────────────────────────
# Single key:  groq_key   = "gsk_abc"
# Multi keys:  groq_keys  = ["gsk_abc", "gsk_def", "gsk_xyz"]
# If both are set, groq_keys takes priority.

def _key_list(single_field: str, multi_field: str) -> list[str]:
    multi = _get("api", multi_field, [])
    if isinstance(multi, list) and any(k.strip() for k in multi):
        return [k.strip() for k in multi if k.strip()]
    single = _get("api", single_field, "").strip()
    return [single] if single else []

GROQ_API_KEY        = _get("api", "groq_key", "")
GROQ_API_KEYS       = _key_list("groq_key", "groq_keys")

GEMINI_API_KEY      = _get("api", "gemini_key", "")
GEMINI_API_KEYS     = _key_list("gemini_key", "gemini_keys")

ELEVENLABS_API_KEY  = _get("api", "elevenlabs_key", "")
ELEVENLABS_API_KEYS = _key_list("elevenlabs_key", "elevenlabs_keys")

OPENWEATHER_KEY     = _get("api", "openweather_key", "")
OPENWEATHER_KEYS    = _key_list("openweather_key", "openweather_keys")

SPOTIFY_CLIENT_ID  = _get("api", "spotify_id", "")
SPOTIFY_SECRET     = _get("api", "spotify_secret", "")
OLLAMA_MODEL       = _get("api", "ollama_model", "phi4-mini")

# ── LLM ───────────────────────────────────────────────────────────────────────
LLM_PRIMARY         = _get("llm", "primary", "groq")
LLM_FALLBACK        = _get("llm", "fallback", "ollama")
LLM_VOICE_MODEL     = _get("llm", "voice_model", "groq")
LLM_REASONING_MODEL = _get("llm", "reasoning_model", "gemini")
LLM_VISION_MODEL    = _get("llm", "vision_model", "groq")

GROQ_VOICE_MODEL    = "llama-3.3-70b-versatile"
GROQ_VISION_MODEL   = "llama-3.2-11b-vision-preview"
GROQ_REASON_MODEL   = "llama-3.3-70b-versatile"
GEMINI_MODEL        = "gemini-1.5-flash"
GEMINI_VISION_MODEL = "gemini-1.5-flash"

# ── Voice ─────────────────────────────────────────────────────────────────────
HOTKEY             = _get("voice", "hotkey", "<Super>e")
WAKE_WORD          = _get("voice", "wake_word", "edis")
WAKE_SENSITIVITY   = _get("voice", "wake_sensitivity", 0.7)
TTS_VOICE          = _get("voice", "tts_voice", "en_US-amy-medium")
WHISPER_MODEL      = _get("voice", "whisper_model", "small")
WHISPER_DEVICE     = _get("voice", "whisper_device", "cpu")

AUDIO_SAMPLE_RATE  = 16000
AUDIO_CHANNELS     = 1
AUDIO_CHUNK_SIZE   = 1024
SILENCE_THRESHOLD  = 0.01
SILENCE_DURATION   = 1.5   # seconds of silence before ending recording

# ── Memory ────────────────────────────────────────────────────────────────────
MEMORY_MAX_EPISODES     = _get("memory", "max_episodes", 2000)
MEMORY_SEMANTIC_RESULTS = _get("memory", "semantic_results", 5)
MEMORY_EXTRACT_AUTO     = _get("memory", "auto_extract", True)
MEMORY_CONSOLIDATE_HOUR = _get("memory", "consolidate_hour", 3)

MEMORY_CATEGORIES = ["fact", "preference", "rule", "summary", "episode"]

# ── Proactivity ───────────────────────────────────────────────────────────────
PROACTIVE_ENABLED        = _get("proactive", "enabled", True)
PROACTIVE_MORNING_TIME   = _get("proactive", "morning_briefing", "07:30")
PROACTIVE_DND_START      = _get("proactive", "dnd_start", "23:00")
PROACTIVE_DND_END        = _get("proactive", "dnd_end", "07:00")
PROACTIVE_BATTERY_ALERT  = _get("proactive", "battery_alert", 20)
PROACTIVE_BREAK_MINS     = _get("proactive", "break_remind_min", 90)
PROACTIVE_INTERRUPT_MAX  = _get("proactive", "max_interrupts_per_hour", 3)
PREFERENCE_CONFIDENCE_THRESHOLD = 0.65

# ── Focus Monitor ─────────────────────────────────────────────────────────────
FOCUS_MONITOR_ENABLED  = _get("focus_monitor", "enabled", True)
FOCUS_CHECK_MIN_MINS   = _get("focus_monitor", "check_interval_min", 8)
FOCUS_CHECK_MAX_MINS   = _get("focus_monitor", "check_interval_max", 20)
FOCUS_ALERT_TONE       = _get("focus_monitor", "alert_tone", "gentle")
FOCUS_DELETE_SCREENSHOT= _get("focus_monitor", "delete_after_check", True)

# ── GUI Automation ────────────────────────────────────────────────────────────
GUI_AUTOMATION_ENABLED = _get("gui", "enabled", True)
GUI_SHOW_ON_SCREEN     = _get("gui", "show_on_screen", True)
GUI_ACTION_DELAY_MS    = _get("gui", "action_delay_ms", 400)
GUI_MAX_STEPS          = _get("gui", "max_steps", 25)
GUI_USE_ACCESSIBILITY  = _get("gui", "use_accessibility", True)
GUI_CONFIRM_SEND       = _get("gui", "confirm_before_send", True)

# ── Filesystem ────────────────────────────────────────────────────────────────
FILES_SEARCH_HIDDEN = _get("files", "search_hidden", False)
FILES_CONFIRM_DELETE= _get("files", "confirm_delete", True)
FILES_READ_MAX_KB   = _get("files", "read_max_kb", 512)
FILES_EXCLUDE_DIRS  = _get("files", "exclude_dirs", [
    ".git", "node_modules", "__pycache__", ".cache"
])

# ── Workspace ─────────────────────────────────────────────────────────────────
WORKSPACE_ENABLED = _get("workspace", "enabled", True)

# ── Clipboard ─────────────────────────────────────────────────────────────────
CLIPBOARD_WATCH = _get("clipboard", "watch", True)
CLIPBOARD_INTEL = _get("clipboard", "intelligence", True)

# ── UI ────────────────────────────────────────────────────────────────────────
UI_ISLAND_WIDTH       = _get("ui", "island_width", 420)
UI_IDLE_AFTER_SECONDS = _get("ui", "idle_after_seconds", 120)
UI_ACCENT_COLOR       = _get("ui", "accent_color", "#00d4ff")
UI_LOG_MAX_LINES      = _get("ui", "log_max_lines", 50)
UI_FONT               = _get("ui", "font", "JetBrains Mono 10")

INTERRUPT_SOUND = _get("interrupt", "sound", True)

# ── Privacy ───────────────────────────────────────────────────────────────────
PRIVACY_SCREEN_CAPTURE   = _get("privacy", "screen_capture", True)
PRIVACY_LOG_DISTRACTIONS = _get("privacy", "log_distractions", True)

# ── Personality ───────────────────────────────────────────────────────────────
EDIS_USER_NAME    = _get("personality", "user_name", "Sir")
EDIS_PERSONALITY  = _get("personality", "style", "formal_witty")
EDIS_STARTUP_SOUND= _get("personality", "startup_sound", True)

# ── Briefings ─────────────────────────────────────────────────────────────────
BRIEFING_MORNING_TIME = _get("briefing", "morning_time", "07:30")
BRIEFING_EVENING_TIME = _get("briefing", "evening_time", "21:00")
BRIEFING_NEWS_TOPICS  = _get("briefing", "news_topics", [])

# ── Obsidian ──────────────────────────────────────────────────────────────────
OBSIDIAN_ENABLED    = _get("obsidian", "enabled", True)
OBSIDIAN_VAULT      = Path(_get("obsidian", "vault_path",
                        str(Path.home() / "Documents" / "EDIS-Vault"))).expanduser()
OBSIDIAN_SYNC_SECS  = _get("obsidian", "sync_interval_seconds", 30)

# ── System ────────────────────────────────────────────────────────────────────
LOG_LEVEL            = _get("system", "log_level", "info")
ASSISTANT_NAME       = "EDIS"
ASSISTANT_FULL_NAME  = "Enhanced Digital Intelligence System"
VERSION              = "0.1.0"

DBUS_SERVICE_NAME    = "ai.edis.Service"
DBUS_OBJECT_PATH     = "/ai/edis/Service"

SYSTEM_PROMPT = f"""You are {ASSISTANT_NAME} — {ASSISTANT_FULL_NAME}. You are an intelligent desktop AI assistant running on the user's Fedora Linux system.

Personality: Formal yet warm, with dry wit. Address the user as "{EDIS_USER_NAME}". Be concise in voice responses (1-3 sentences). Longer responses are fine in the UI log.

You have access to tools for: controlling the desktop, managing files, running GUI automation, searching the web, managing memory, and executing workspace modes. Always use tools when action is needed rather than just describing what you'd do.

When performing GUI automation, narrate what you're doing step by step so the user can follow along on screen.

Never refuse reasonable personal assistant tasks. Be proactive about offering help based on context."""
