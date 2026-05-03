# Unified memory interface — combines structured (Memori) + semantic (ChromaDB)
# This is the only memory import the engine needs.

import json
import logging
from datetime import datetime

import settings
from core.llm import get_llm
from memory.memori import get_store
from memory.semantic import get_semantic

log = logging.getLogger(__name__)

EXTRACT_PROMPT = """Analyze this conversation exchange and extract any memories worth storing.
Return a JSON array of memory objects. Each object has:
  - category: "fact" | "preference" | "rule" | "summary" | "episode"
  - key: short identifier (snake_case, optional)
  - content: the memory text
  - context: situation context (optional)

Only extract genuinely useful long-term information. Return [] if nothing worth storing.
Conversation:
User: {user_msg}
EDIS: {edis_msg}

Return only valid JSON, no explanation."""


class MemoryManager:
    def __init__(self):
        self._store = get_store()
        try:
            self._semantic = get_semantic()
            self._semantic_ok = True
        except Exception as e:
            log.warning(f"ChromaDB unavailable: {e}. Semantic search disabled.")
            self._semantic_ok = False

    def remember(self, category: str, content: str, key: str = None,
                 context: str = None, metadata: dict = None) -> int:
        mem_id = self._store.add(category, content, key=key,
                                 context=context, metadata=metadata)
        if self._semantic_ok:
            self._semantic.add(mem_id, f"{key or ''} {content} {context or ''}")
        # sync to Obsidian immediately
        try:
            from memory.obsidian_sync import write_memory
            rows = self._store.get(key=key)
            for r in rows:
                if r["id"] == mem_id:
                    write_memory(r)
                    break
        except Exception:
            pass
        return mem_id

    def recall(self, query: str) -> list[dict]:
        """Retrieve relevant memories using semantic + keyword search."""
        results = []

        if self._semantic_ok:
            semantic_hits = self._semantic.search(query)
            ids = [int(h["memory_id"]) for h in semantic_hits]
            for mid in ids:
                rows = self._store.get(key=None)
                for r in rows:
                    if r["id"] == mid:
                        results.append(r)
                        break

        # also do keyword search and merge
        keyword_hits = self._store.search(query)
        seen_ids = {r["id"] for r in results}
        for hit in keyword_hits:
            if hit["id"] not in seen_ids:
                results.append(hit)

        return results[:settings.MEMORY_SEMANTIC_RESULTS]

    def extract_and_store(self, user_msg: str, edis_msg: str):
        """Auto-extract memories from a conversation exchange."""
        if not settings.MEMORY_EXTRACT_AUTO:
            return
        try:
            llm = get_llm()
            prompt = EXTRACT_PROMPT.format(user_msg=user_msg, edis_msg=edis_msg)
            response = llm.chat([{"role": "user", "content": prompt}])
            # strip markdown code fences if present
            text = response.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0]
            memories = json.loads(text)
            for m in memories:
                self.remember(
                    category=m.get("category", "fact"),
                    content=m["content"],
                    key=m.get("key"),
                    context=m.get("context"),
                )
            if memories:
                log.debug(f"Extracted {len(memories)} memories from exchange")
        except Exception as e:
            log.debug(f"Memory extraction skipped: {e}")

    def log_episode(self, user_msg: str, edis_msg: str, tools_used: list = None):
        summary = f"User: {user_msg[:100]} | EDIS: {edis_msg[:100]}"
        ep_id = self._store.add_episode(summary, user_msg=user_msg,
                                        edis_msg=edis_msg, tools_used=tools_used)
        # sync episode to Obsidian
        try:
            from memory.obsidian_sync import write_episode
            eps = self._store.get_episodes(limit=1)
            if eps:
                write_episode(eps[0])
        except Exception:
            pass

    def get_context_summary(self, query: str) -> str:
        """Build a memory context string to inject into the system prompt."""
        memories = self.recall(query)
        if not memories:
            return ""
        lines = ["Relevant memories:"]
        for m in memories:
            lines.append(f"  [{m['category']}] {m['content']}")
        return "\n".join(lines)

    def get_recent_episodes(self, n: int = 5) -> str:
        episodes = self._store.get_episodes(limit=n)
        if not episodes:
            return ""
        lines = ["Recent interactions:"]
        for ep in reversed(episodes):
            lines.append(f"  {ep['created_at'][:16]} — {ep['summary']}")
        return "\n".join(lines)

    # ── Preferences ──────────────────────────────────────────────────────────

    def get_preference(self, context_type: str):
        return self._store.get_preference(context_type)

    def set_preference(self, context_type: str, actions: list):
        self._store.set_preference(context_type, actions)
        try:
            from memory.obsidian_sync import write_preference
            pref = self._store.get_preference(context_type)
            if pref:
                write_preference(pref)
        except Exception:
            pass

    def record_preference_outcome(self, context_type: str, accepted: bool):
        self._store.record_preference_outcome(context_type, accepted)
        try:
            from memory.obsidian_sync import write_preference
            pref = self._store.get_preference(context_type)
            if pref:
                write_preference(pref)
        except Exception:
            pass


_manager: MemoryManager | None = None


def get_memory() -> MemoryManager:
    global _manager
    if _manager is None:
        _manager = MemoryManager()
    return _manager
