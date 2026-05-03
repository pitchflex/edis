# Obsidian sync — writes all EDIS memory to markdown files in real time.
# Open ~/Documents/EDIS-Vault in Obsidian for a live visual memory graph.

import json
import logging
import threading
import time
from datetime import datetime
from pathlib import Path

import settings

log = logging.getLogger(__name__)

# ── Vault structure ───────────────────────────────────────────────────────────
#
#  EDIS-Vault/
#  ├── 🏠 EDIS Dashboard.md
#  ├── Memory/
#  │   ├── Facts/
#  │   ├── Preferences/
#  │   ├── Rules/
#  │   ├── Summaries/
#  │   └── Episodes/
#  │       └── 2026-05-03/
#  └── Workspace Modes/


def _vault() -> Path:
    return settings.OBSIDIAN_VAULT


def _ensure_dirs():
    for d in [
        _vault() / "Memory" / "Facts",
        _vault() / "Memory" / "Preferences",
        _vault() / "Memory" / "Rules",
        _vault() / "Memory" / "Summaries",
        _vault() / "Memory" / "Episodes",
        _vault() / "Workspace Modes",
    ]:
        d.mkdir(parents=True, exist_ok=True)


# ── Individual memory writers ─────────────────────────────────────────────────

def _category_dir(category: str) -> Path:
    mapping = {
        "fact":       "Memory/Facts",
        "preference": "Memory/Preferences",
        "rule":       "Memory/Rules",
        "summary":    "Memory/Summaries",
        "episode":    "Memory/Episodes",
    }
    return _vault() / mapping.get(category, "Memory/Facts")


def _confidence_bar(confidence: float) -> str:
    filled = int(confidence * 10)
    return "█" * filled + "░" * (10 - filled) + f" {confidence:.0%}"


def write_memory(memory: dict):
    """Write a single memory entry as an Obsidian markdown file."""
    if not settings.OBSIDIAN_ENABLED:
        return
    try:
        cat = memory.get("category", "fact")
        mid = memory.get("id", 0)
        key = memory.get("key") or f"{cat}_{mid}"
        content = memory.get("content", "")
        context = memory.get("context", "")
        confidence = memory.get("confidence", 1.0)
        created = memory.get("created_at", "")[:19].replace("T", " ")
        updated = memory.get("updated_at", "")[:19].replace("T", " ")

        safe_key = key.replace("/", "-").replace("\\", "-")[:60]
        out_dir = _category_dir(cat)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{safe_key}.md"

        tag = f"#{cat}"
        context_link = f"[[{context}]]" if context else ""
        conf_bar = _confidence_bar(confidence)

        md = f"""---
id: {mid}
category: {cat}
key: {key}
confidence: {confidence}
created: "{created}"
updated: "{updated}"
tags: [edis, memory, {cat}]
---

# {content}

| Field | Value |
|---|---|
| Category | `{cat}` |
| Key | `{key}` |
| Confidence | {conf_bar} |
| Context | {context_link or "—"} |
| Created | {created} |
| Updated | {updated} |

---

*{tag} · [[EDIS Dashboard]]*
"""
        path.write_text(md)
    except Exception as e:
        log.debug(f"Obsidian write_memory failed: {e}")


def write_preference(pref: dict):
    """Write a learned preference as an Obsidian note."""
    if not settings.OBSIDIAN_ENABLED:
        return
    try:
        ctx = pref.get("context_type", "unknown")
        actions_raw = pref.get("actions", "[]")
        actions = json.loads(actions_raw) if isinstance(actions_raw, str) else actions_raw
        confidence = pref.get("confidence", 1.0)
        accepts = pref.get("accepts", 0)
        declines = pref.get("declines", 0)
        updated = pref.get("updated_at", "")[:19].replace("T", " ")

        out_dir = _vault() / "Memory" / "Preferences"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{ctx}.md"

        actions_md = "\n".join(f"- {a}" for a in actions)
        conf_bar = _confidence_bar(confidence)
        total = accepts + declines
        accept_rate = f"{accepts}/{total}" if total else "0/0"

        md = f"""---
context_type: {ctx}
confidence: {confidence}
accepts: {accepts}
declines: {declines}
updated: "{updated}"
tags: [edis, preference, {ctx}]
---

# Preference — {ctx.replace("_", " ").title()}

When {settings.EDIS_USER_NAME} starts a **{ctx.replace("_", " ")}**, EDIS offers:

{actions_md}

## Stats

| | |
|---|---|
| Confidence | {conf_bar} |
| Accepted | {accept_rate} times |
| Last updated | {updated} |

---

*#preference · [[EDIS Dashboard]]*
"""
        path.write_text(md)
    except Exception as e:
        log.debug(f"Obsidian write_preference failed: {e}")


def write_episode(episode: dict):
    """Write a conversation episode as a dated Obsidian note."""
    if not settings.OBSIDIAN_ENABLED:
        return
    try:
        eid = episode.get("id", 0)
        user_msg = episode.get("user_msg", "")
        edis_msg = episode.get("edis_msg", "")
        tools_raw = episode.get("tools_used", "[]")
        tools = json.loads(tools_raw) if isinstance(tools_raw, str) else tools_raw
        created = episode.get("created_at", "")[:19]
        date_str = created[:10]
        time_str = created[11:16] if len(created) > 10 else ""

        day_dir = _vault() / "Memory" / "Episodes" / date_str
        day_dir.mkdir(parents=True, exist_ok=True)
        path = day_dir / f"{time_str.replace(':', '-')} — episode {eid}.md"

        tools_md = ""
        if tools:
            tools_md = "\n**Tools used:** " + ", ".join(f"`{t}`" for t in tools)

        md = f"""---
id: {eid}
date: "{date_str}"
time: "{time_str}"
tags: [edis, episode, {date_str}]
---

# {date_str} {time_str}

> **{settings.EDIS_USER_NAME}:** {user_msg}

**EDIS:** {edis_msg}
{tools_md}

---

*#episode · [[{date_str}]] · [[EDIS Dashboard]]*
"""
        path.write_text(md)
    except Exception as e:
        log.debug(f"Obsidian write_episode failed: {e}")


def write_workspace_mode(name: str, actions: list):
    """Write a workspace mode as an Obsidian note."""
    if not settings.OBSIDIAN_ENABLED:
        return
    try:
        out_dir = _vault() / "Workspace Modes"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{name}.md"

        actions_md = "\n".join(
            f"- **{a.get('type', '?')}**: `{a.get('value', '')}`"
            for a in actions
        )

        md = f"""---
mode: {name}
actions: {len(actions)}
tags: [edis, workspace, {name.replace(" ", "_")}]
---

# Workspace Mode — {name.title()}

## Actions

{actions_md}

---

*#workspace · [[EDIS Dashboard]]*
"""
        path.write_text(md)
    except Exception as e:
        log.debug(f"Obsidian write_workspace_mode failed: {e}")


# ── Dashboard ─────────────────────────────────────────────────────────────────

def write_dashboard():
    """Regenerate the EDIS Dashboard overview note."""
    if not settings.OBSIDIAN_ENABLED:
        return
    try:
        from memory.memori import get_store
        store = get_store()

        facts  = store.get(category="fact", limit=1000)
        prefs  = store.all_preferences()
        rules  = store.get(category="rule", limit=1000)
        eps    = store.get_episodes(limit=5)

        # workspace modes
        modes = [
            r["key"].replace("workspace_mode_", "")
            for r in rules if r.get("key", "").startswith("workspace_mode_")
        ]

        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        # recent episodes summary
        ep_lines = ""
        for ep in reversed(eps):
            t = ep.get("created_at", "")[:16].replace("T", " ")
            s = ep.get("user_msg", "")[:60]
            ep_lines += f"- `{t}` — {s}\n"

        # preferences summary
        pref_lines = ""
        for p in prefs:
            ctx = p["context_type"]
            conf = p["confidence"]
            pref_lines += f"- [[{ctx}]] — confidence {conf:.0%}\n"

        # workspace modes
        mode_lines = "\n".join(f"- [[{m}]]" for m in modes) or "— none saved yet"

        md = f"""---
updated: "{now}"
tags: [edis, dashboard]
---

# 🤖 EDIS Dashboard

> Enhanced Digital Intelligence System — Memory Overview
> Last updated: `{now}`

---

## Memory Stats

| Category | Count |
|---|---|
| Facts | {len(facts)} |
| Preferences | {len(prefs)} |
| Rules | {len(rules)} |

---

## Learned Preferences

{pref_lines or "— none yet"}

---

## Workspace Modes

{mode_lines}

---

## Recent Episodes

{ep_lines or "— no episodes yet"}

---

## Quick Links

- [[Memory/Facts/]] — all facts
- [[Memory/Preferences/]] — all preferences
- [[Memory/Episodes/]] — conversation log
- [[Workspace Modes/]] — saved modes

---

*Auto-generated by EDIS · {settings.ASSISTANT_FULL_NAME}*
"""
        (_vault() / "🏠 EDIS Dashboard.md").write_text(md)
    except Exception as e:
        log.debug(f"Dashboard write failed: {e}")


# ── Full sync (rebuilds everything from DB) ───────────────────────────────────

def full_sync():
    """Rebuild entire Obsidian vault from current DB state."""
    if not settings.OBSIDIAN_ENABLED:
        return
    log.info(f"Obsidian full sync → {_vault()}")
    _ensure_dirs()

    from memory.memori import get_store
    from workspace.orchestrator import get_orchestrator
    import json

    store = get_store()

    for cat in ["fact", "preference", "rule", "summary"]:
        for mem in store.get(category=cat, limit=10000):
            write_memory(mem)

    for pref in store.all_preferences():
        write_preference(pref)

    for ep in store.get_episodes(limit=settings.MEMORY_MAX_EPISODES):
        write_episode(ep)

    # workspace modes
    orch = get_orchestrator()
    for mode_name in orch.all_modes():
        actions = orch.get_mode(mode_name) or []
        write_workspace_mode(mode_name, actions)

    write_dashboard()
    log.info("Obsidian sync complete")


# ── Background sync loop ──────────────────────────────────────────────────────

_sync_thread: threading.Thread | None = None
_running = False


def start_background_sync():
    """Refresh dashboard + new entries every N seconds in background."""
    global _sync_thread, _running
    if not settings.OBSIDIAN_ENABLED:
        return
    _running = True
    _ensure_dirs()
    # do a full sync on startup
    threading.Thread(target=full_sync, daemon=True).start()

    def _loop():
        while _running:
            time.sleep(settings.OBSIDIAN_SYNC_SECS)
            try:
                write_dashboard()
            except Exception as e:
                log.debug(f"Obsidian background sync error: {e}")

    _sync_thread = threading.Thread(target=_loop, daemon=True)
    _sync_thread.start()
    log.info(f"Obsidian sync started — vault: {_vault()}")


def stop_background_sync():
    global _running
    _running = False
