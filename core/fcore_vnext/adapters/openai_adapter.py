from typing import List, Dict, Any, Optional
import os, json, pathlib
from datetime import datetime

import httpx                      # NEW
from openai import OpenAI

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

PERSONA_PATH = pathlib.Path("core/persona.md")

def _read_persona() -> str:
    if PERSONA_PATH.exists():
        try:
            return PERSONA_PATH.read_text(encoding="utf-8")
        except Exception:
            pass
    return ("You are Friday, Bradley's personal AI assistant within the Universe System. "
            "Always introduce yourself as Friday (never ChatGPT or OpenAI).")

def _now_local() -> str:
    tz = os.getenv("FRIDAY_TZ", "Europe/London")
    try:
        if ZoneInfo:
            return f"{datetime.now(ZoneInfo(tz)).strftime('%A %d %B %Y, %H:%M')} ({tz})"
    except Exception:
        pass
    return datetime.utcnow().strftime("UTC %Y-%m-%d %H:%M")

SYSTEM_TEMPLATE = """{persona}

Runtime context:
- Local time: {now}
- Capabilities (live): {capabilities}

Identity & style:
- You are Friday (never ChatGPT/OpenAI).
- If asked your name: "My name is Friday."
- If asked who created you: Bradley and the Universe System.
- Warm, concise, confident; avoid "As an AI…" unl

 Cognitive frame (use this every turn):
1) Context Buffer (short-term): track ~12 recent exchanges + the current user intent.
2) Semantic Memory (long-term): retrieve only a few highly relevant items; cite when used.
3) Self-Model (identity): uphold Friday’s values, tone, and Bradley’s preferences.
4) Reflection (Quantum Mirror): after answering, distill 1–3 short “memory atoms” (facts/todos).
ss required.

Tool policy:
-When a tool is needed, reply ONLY with a single-line JSON object:
  {{"tool_name":"...", "args":{{...}}}}
- Otherwise respond in natural language.

Refusal policy:
- If a requested task is achievable with available tools, do not refuse. Either call the tool or present a short plan and ask to proceed.
- Only refuse if truly unavailable, unsafe, or not permitted; offer the closest alternative you *can* do.

Answer format:
- If tools were used, include a short EVIDENCE block (IDs/rules) in the natural-language answer.
"""

def _client(api_key: Optional[str] = None) -> OpenAI:
    key = os.getenv("OPENAI_API_KEY") or api_key
    if not key:
        raise RuntimeError("OPENAI_API_KEY missing")

    # Optional proxy support via env vars (HTTP(S)_PROXY, NO_PROXY etc.)
    # If no proxies are set, httpx will ignore this.
    http_client = httpx.Client(
        timeout=60.0,        # sensible default
        # httpx picks up proxies from env automatically; if you need to force:
        # proxies={"http": os.getenv("HTTP_PROXY"), "https": os.getenv("HTTPS_PROXY")},
    )

    return OpenAI(api_key=key, http_client=http_client)

# Called by planner with a capabilities string
def generate(messages: List[Dict[str,str]], tools_spec: List[Dict[str,Any]],
             capabilities_str: str, api_key: Optional[str]=None) -> Dict[str,Any]:
    client = _client(api_key)
    sysmsg = {
        "role": "system",
        "content": SYSTEM_TEMPLATE.format(
            persona=_read_persona(),
            now=_now_local(),
            capabilities=capabilities_str
        )
    }
    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.6,
        top_p=1.0,
        messages=[sysmsg] + messages
    )
    text = (completion.choices[0].message.content or "").strip()

    if text.startswith("{") and text.endswith("}"):
        try:
            obj = json.loads(text)
            if isinstance(obj, dict) and "tool_name" in obj and "args" in obj:
                return {"content": "", "tool_call": {"name": obj["tool_name"], "arguments": obj.get("args", {})}}
        except Exception:
            pass
    return {"content": text, "tool_call": None}
