import os, toml, requests, io, sys, json
from dotenv import load_dotenv
from fastapi import FastAPI, File, UploadFile, Response, HTTPException, Request
from fastapi.responses import JSONResponse
from zoneinfo import ZoneInfo
from datetime import datetime
from fastapi.middleware.cors import CORSMiddleware
from serpapi import GoogleSearch
from .registry import Registry
from .planner import Planner
from .executor import Executor
from .sandbox import Sandbox
from pydantic import BaseModel
from typing import List
#f# rom .memory_store import save_text as mem_save_text, upsert_embedding as mem_upsert_embedding, search as mem_search

# Add plugins directory to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'plugins'))

# Load core/.env (non-overriding)
CORE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
load_dotenv(os.path.join(CORE_DIR, '.env'), override=False)

# Import memory embeddings plugin
try:
    from memory_embeddings.tool import TOOLS as MEMORY_TOOLS
except ImportError:
    MEMORY_TOOLS = {}

# Pydantic models
class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[Message]

# Configuration loading
CONFIG_PATH = "config/settings.toml"
CONFIG = toml.load(CONFIG_PATH) if os.path.isfile(CONFIG_PATH) else toml.load("config/settings.example.toml")

# Helper function to get config value with environment variable fallback
def get_config_value(section, key, env_var_name):
    """Get config value, preferring environment variable over config file"""
    env_value = os.environ.get(env_var_name)
    if env_value:
        return env_value
    return CONFIG.get(section, {}).get(key, "")

# Initialize Registry
registry = Registry(plugins_root="plugins")
registry.load()

# Initialize Planner and Executor  
sandbox = Sandbox()
planner = Planner(registry, sandbox, get_config_value("auth", "openai_api_key", "OPENAI_API_KEY"))
executor = Executor(registry)

# Workspace root for file operations
WORKSPACE_ROOT = os.path.abspath(".")

app = FastAPI()

# Enable CORS for UI dev origins and Tailscale *.ts.net domains
ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=r"^https://.*\.ts\.net$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Timezone configuration
TZ = CONFIG.get("timezone", {}).get("tz", "UTC")

def now_local():
    """Get current time in configured timezone"""
    return datetime.now(ZoneInfo(TZ))

def transcribe_audio(audio_data: bytes, filename: str, api_key: str) -> str:
    """Transcribe audio data using OpenAI Whisper API"""
    if not api_key:
        raise HTTPException(status_code=400, detail="OpenAI API key not configured")
    
    try:
        # Create a file-like object for the API call
        files = {
            "file": (filename, io.BytesIO(audio_data), "audio/webm"),
            "model": (None, "whisper-1")
        }
        
        headers = {
            "Authorization": f"Bearer {api_key}"
        }
        
        response = requests.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers=headers,
            files=files
        )
        
        if response.status_code == 200:
            result = response.json()
            return result.get("text", "")
        else:
            raise HTTPException(status_code=response.status_code, detail=f"OpenAI API error: {response.status_code}")
            
    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")
@app.get("/health")
def health():
    current_time = now_local()
    return {
        "status": "ok",
        "timezone": TZ,
        "current_time": current_time.isoformat(),
        "current_time_formatted": current_time.strftime("%A %d %B %Y, %H:%M"),
        "checks": {
            "config_loaded": True,
            "openai_key_present": bool(get_config_value("auth", "openai_api_key", "OPENAI_API_KEY")),
            "serpapi_key_present": bool(get_config_value("web", "serpapi_api_key", "SERPAPI_API_KEY")), 
            "elevenlabs_key_present": bool(get_config_value("voice", "elevenlabs_api_key", "ELEVENLABS_API_KEY"))
        }
    }

@app.get("/api/health")
def api_health_alias():
    return health()
@app.get("/tools")
def tools():
    return {"tools": registry.list_tools()}
@app.post("/chat")
def chat(req: ChatRequest, request: Request):
    try:
        # Live context
        os.environ["NOW_OVERRIDE"] = now_local().strftime("%A %d %B %Y, %H:%M")
        os.environ["TZ_OVERRIDE"] = TZ

        messages = [m.model_dump() for m in req.messages]
messages = messages[-12:]

        # Persona system prompt
        persona = CONFIG.get("persona", {}) or {}
        p_name = persona.get("name", "Friday")
        p_tone = persona.get("tone", "warm, proactive")
        p_principles = persona.get("principles", ["clarity", "honesty"]) or []
        bullets = "\n".join([f"- {p}" for p in p_principles])
        sys_msg = f"You are {p_name}.\nTone: {p_tone}.\nPrinciples:\n{bullets}"
        user_hdr = request.headers.get("X-User-Name")
        if user_hdr:
            sys_msg += f"\nUser is {user_hdr}."
        messages.insert(0, {"role": "system", "content": sys_msg})

        # Memory search (local store)
        user_message = req.messages[-1].content if req.messages else ""
       try:
        if user_message:
            # Ask plugin for top memories
            mres = registry.run("memory_search", {"query": user_message, "k": 5, "threshold": 0.35}) or {}
            rows = (mres.get("results") or [])[:5]
            notes = [r.get("text") for r in rows if r.get("text")]
            if notes:
                memo = "Relevant memories:\n- " + "\n- ".join(notes)
                messages.insert(1, {"role": "system", "content": memo[:2000]})
except Exception as e:
        print(f"Local memory search error: {e}")
        # Encourage KG/rules
        messages.insert(1, {"role": "system", "content": "Use KG and rules when helpful; always cite evidence if you used them."})

        first = planner.step(messages)
        if first.get("tool_call"):
            call = first["tool_call"]
            result = executor.run_tool(
                call["name"], call["arguments"],
                {"workspace_root": WORKSPACE_ROOT,
                 "serpapi_key": os.getenv("SERPAPI_API_KEY") or get_config_value("web", "serpapi_api_key", "SERPAPI_API_KEY")}
            )
            messages.append({"role": "assistant", "content": json.dumps({"tool_result": result})})
            second = planner.step(messages)
            final_response = {"content": second.get("content",""), "tool_used": call["name"], "intermediate": result}
        else:
            final_response = {"content": first.get("content",""), "tool_used": None}

       # === Quantum Mirror: always write a journal entry ===
        try:
            registry.run("journal_write", {
                "user_message": user_message,
                "friday_response": final_response.get("content", ""),
                "tool_used": final_response.get("tool_used")
            })
        except Exception as e:
            print("[journal] write failed:", e)
        # === Reflection step: extract memory atoms (facts/todos) and save via plugin ===
        try:
            if user_message and final_response.get("content"):
                reflect_msgs = [
                    {"role":"system","content":"Extract up to 3 short memory atoms from the exchange. JSON only: {\"facts\":[...],\"todos\":[...]}"},
                    {"role":"user","content": f"User said: {user_message}\nFriday replied: {final_response.get('content','')}"}
                ]
                atoms_resp = __import__("core.fcore_vnext.adapters.openai_adapter", fromlist=["openai_adapter"]).openai_adapter.generate(
                    reflect_msgs, [], "[]", api_key=get_config_value("auth","openai_api_key","OPENAI_API_KEY")
                )
                data = json.loads(atoms_resp.get("content") or "{}")
                for t in (data.get("facts") or [])[:3]:
                    registry.run("memory_save", {"text": str(t)[:280]})
                for td in (data.get("todos") or [])[:3]:
                    registry.run("memory_save", {"text": ("TODO: " + str(td))[:280]})
        except Exception as e:
            

    ### return final_response
        return final_response
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/chat")
def chat_alias(req: ChatRequest, request: Request):
    # Route alias to support clients calling /api/chat
    return chat(req, request)

@app.post("/run")
def run_tool(req: dict):
    tool_name = req.get("tool_name", "")
    args = req.get("args", {})
    
    # Handle web_search separately since it's not in the registry yet
    if tool_name == "web_search":
        query = args.get("query", "")
        num = args.get("num", 3)
        
        # Check if API key is configured (prefer environment variable)
        api_key = get_config_value("web", "serpapi_api_key", "SERPAPI_API_KEY")
        if not api_key:
            # Return stub data if no API key
            return {
                "results": [
                    {"title": f"Stub result {i+1} for: {query}", 
                     "snippet": f"This is a stub search result for '{query}'. Configure SerpAPI key to get real results.",
                     "link": f"https://example.com/{i+1}"}
                    for i in range(num)
                ]
            }
        
        # Use real SerpAPI
        search = GoogleSearch({
            "q": query,
            "api_key": api_key,
            "num": num
        })
        
        results = search.get_dict()
        organic_results = results.get("organic_results", [])[:num]
        
        return {
            "results": [
                {
                    "title": result.get("title", ""),
                    "snippet": result.get("snippet", ""),
                    "link": result.get("link", "")
                }
                for result in organic_results
            ]
        }
    
    # Use Registry for all other tools
    return registry.run(tool_name, args)

@app.post("/api/run")
def run_alias(req: dict):
    # Route alias to support clients calling /api/run
    return run_tool(req)

@app.get("/__where")
def where():
    import pathlib, inspect
    return {"file": str(pathlib.Path(inspect.getfile(where)).resolve())}

@app.post("/voice/speak")
def text_to_speech(req: dict):
    """Convert text to speech using ElevenLabs"""
    text = req.get("text", "")
    if not text:
        return {"error": "No text provided"}
    
    api_key = get_config_value("voice", "elevenlabs_api_key", "ELEVENLABS_API_KEY")
    voice_id = CONFIG.get("voice", {}).get("voice_id", "EXAVITQu4vr4xnSDxMaL")
    
    if not api_key:
        return {"error": "ElevenLabs API key not configured"}
    
    try:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": api_key
        }
        data = {
            "text": text,
            "model_id": "eleven_monolingual_v1",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.5
            }
        }
        
        response = requests.post(url, json=data, headers=headers)
        
        if response.status_code == 200:
            return Response(content=response.content, media_type="audio/mpeg")
        else:
            return {"error": f"ElevenLabs API error: {response.status_code}"}
            
    except Exception as e:
        return {"error": f"Voice synthesis failed: {str(e)}"}

@app.post("/voice/transcribe")
async def voice_transcribe(file: UploadFile = File(None), audio: UploadFile = File(None)):
    up = file or audio
    if not up:
        raise HTTPException(status_code=400, detail="No audio file provided (use 'file' or 'audio')")
    data = await up.read()
    text = transcribe_audio(
        data,
        up.filename or "input.webm",
        api_key=get_config_value("auth", "openai_api_key", "OPENAI_API_KEY")
    )
    return {"text": text}

def _is_local(request: Request) -> bool:
    return (request.client and request.client.host in ("127.0.0.1", "::1"))

def _embed_text(text: str):
    key = get_config_value("auth", "openai_api_key", "OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY missing")
    resp = requests.post(
        "https://api.openai.com/v1/embeddings",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        json={
            "model": "text-embedding-3-large",
            "input": text,
        },
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"OpenAI embeddings error: {resp.status_code} {resp.text[:200]}")
    data = resp.json()
    return data["data"][0]["embedding"]

@app.post("/memory/save")
def memory_save(req: dict, request: Request):
    if not _is_local(request):
        raise HTTPException(status_code=403, detail="Local access only")
    text = (req or {}).get("text", "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    emb = _embed_text(text)
    mid = mem_save_text(text)
    mem_upsert_embedding(mid, text, emb)
    return {"ok": True, "id": mid}

@app.post("/memory/search")
def memory_search(req: dict, request: Request):
    if not _is_local(request):
        raise HTTPException(status_code=403, detail="Local access only")
    query = (req or {}).get("query", "").strip()
    top_k = int((req or {}).get("top_k", 5))
    if not query:
        return {"results": []}
    q_emb = _embed_text(query)
    results = mem_search(q_emb, top_k=top_k)
    return {"results": results}
