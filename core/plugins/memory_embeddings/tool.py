import os, sqlite3, json, numpy as np
import httpx
from typing import List, Dict, Any
from openai import OpenAI

DB = os.path.join("memory", "memdb.sqlite")

def _client():
    key = os.getenv("OPENAI_API_KEY")
    if not key: raise RuntimeError("OPENAI_API_KEY missing")
    http_client = httpx.Client(timeout=60.0)
    return OpenAI(api_key=key, http_client=http_client)

def _ensure():
    os.makedirs("memory", exist_ok=True)
    with sqlite3.connect(DB) as con:
        con.execute("""CREATE TABLE IF NOT EXISTS memories(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            emb BLOB NOT NULL,
            ts DATETIME DEFAULT CURRENT_TIMESTAMP
        )""")

def _embed(text: str) -> np.ndarray:
    cli = _client()
    emb = cli.embeddings.create(model="text-embedding-3-small", input=text)
    vec = np.array(emb.data[0].embedding, dtype=np.float32)
    return vec

def _cos(a: np.ndarray, b: np.ndarray) -> float:
    na = np.linalg.norm(a); nb = np.linalg.norm(b)
    if na == 0 or nb == 0: return 0.0
    return float(np.dot(a, b) / (na * nb))

def get_tools() -> List[Dict[str, Any]]:
    return [
        {"name":"memory_save","description":"Save memory text",
         "parameters":{"type":"object","properties":{"text":{"type":"string"}},"required":["text"]}},
        {"name":"memory_search","description":"Semantic search",
         "parameters":{"type":"object","properties":{"query":{"type":"string"},"k":{"type":"integer","default":5},"threshold":{"type":"number","default":0.35}},"required":["query"]}},
    ]

def run_tool(name: str, args: dict, ctx: dict) -> Dict[str, Any]:
    _ensure()
    if name == "memory_save":
        text = args["text"]
        vec = _embed(text).tobytes()
        with sqlite3.connect(DB) as con:
            con.execute("INSERT INTO memories(text, emb) VALUES (?,?)", (text, vec))
        return {"ok": True}
    if name == "memory_search":
        q = args["query"]; k = int(args.get("k", 5)); thr = float(args.get("threshold", 0.35))
        qv = _embed(q)
        rows = []
        with sqlite3.connect(DB) as con:
            for mid, text, emb, ts in con.execute("SELECT id,text,emb,ts FROM memories"):
                v = np.frombuffer(emb, dtype=np.float32)
                s = _cos(qv, v)
                rows.append((s, {"id":mid,"text":text,"ts":ts,"score":round(s,3)}))
        rows.sort(key=lambda x: x[0], reverse=True)
        return {"results":[r[1] for r in rows if r[0] >= thr][:k]}
    raise ValueError(f"Unknown tool {name}")
