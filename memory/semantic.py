# Semantic memory — ChromaDB embedded, vector similarity search

import logging
from pathlib import Path

import settings

log = logging.getLogger(__name__)


class SemanticStore:
    def __init__(self):
        import chromadb
        settings.CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(settings.CHROMA_DIR))
        self._col = self._client.get_or_create_collection(
            name="edis_memory",
            metadata={"hnsw:space": "cosine"},
        )
        log.info(f"ChromaDB loaded — {self._col.count()} vectors")

    def add(self, memory_id: int, text: str, metadata: dict = None):
        self._col.upsert(
            ids=[str(memory_id)],
            documents=[text],
            metadatas=[metadata or {}],
        )

    def search(self, query: str, n_results: int = None) -> list[dict]:
        n = n_results or settings.MEMORY_SEMANTIC_RESULTS
        count = self._col.count()
        if count == 0:
            return []
        results = self._col.query(
            query_texts=[query],
            n_results=min(n, count),
        )
        out = []
        for i, doc in enumerate(results["documents"][0]):
            out.append({
                "memory_id": results["ids"][0][i],
                "text": doc,
                "distance": results["distances"][0][i],
                "metadata": results["metadatas"][0][i],
            })
        return out

    def delete(self, memory_id: int):
        try:
            self._col.delete(ids=[str(memory_id)])
        except Exception:
            pass

    def count(self) -> int:
        return self._col.count()


_semantic: SemanticStore | None = None


def get_semantic() -> SemanticStore:
    global _semantic
    if _semantic is None:
        _semantic = SemanticStore()
    return _semantic
