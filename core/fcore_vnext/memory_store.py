import os
import json
import hashlib
from datetime import datetime, timezone
from typing import List, Dict
import math


BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "memory"))
JOURNAL_PATH = os.path.join(BASE_DIR, "journal.md")
VECTORS_PATH = os.path.join(BASE_DIR, "vectors.json")


def _ensure_dirs() -> None:
    os.makedirs(BASE_DIR, exist_ok=True)


def _load_vectors() -> List[Dict]:
    if not os.path.isfile(VECTORS_PATH):
        return []
    try:
        with open(VECTORS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return []
    except Exception:
        return []


def _save_vectors(items: List[Dict]) -> None:
    tmp_path = VECTORS_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(items, f)
    os.replace(tmp_path, VECTORS_PATH)


def save_text(text: str) -> str:
    _ensure_dirs()
    now = datetime.now(timezone.utc).isoformat()
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
    entry_id = f"{now}_{digest}"
    line = f"- {now} — {text}\n"
    with open(JOURNAL_PATH, "a", encoding="utf-8") as f:
        f.write(line)
    return entry_id


def upsert_embedding(id: str, text: str, embedding: List[float]) -> None:
    _ensure_dirs()
    items = _load_vectors()
    updated = False
    for it in items:
        if it.get("id") == id:
            it["text"] = text
            it["embedding"] = embedding
            updated = True
            break
    if not updated:
        items.append({"id": id, "text": text, "embedding": embedding})
    _save_vectors(items)


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0 or nb == 0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def search(query_embedding: List[float], top_k: int = 5) -> List[Dict]:
    items = _load_vectors()
    scored = []
    for it in items:
        emb = it.get("embedding") or []
        score = _cosine(query_embedding, emb)
        scored.append({"text": it.get("text", ""), "score": float(score)})
    scored.sort(key=lambda r: r["score"], reverse=True)
    return scored[: max(0, int(top_k))]

