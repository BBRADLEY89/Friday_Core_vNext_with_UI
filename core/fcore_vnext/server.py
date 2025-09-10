import os, toml, requests, io, sys, json
from fastapi import FastAPI, File, UploadFile, Response, HTTPException
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

# Add plugins directory to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'plugins'))

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

# Enable CORS for UI dev origins
ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
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
@app.get("/tools")
def tools():
    return {"tools": registry.list_tools()}
@app.post("/chat")
def chat(req: ChatRequest):
    # Set live context for persona system
    os.environ["NOW_OVERRIDE"] = now_local().strftime("%A %d %B %Y, %H:%M")
    os.environ["TZ_OVERRIDE"] = TZ
    
    messages = [m.model_dump() for m in req.messages]
    
    # Limit to last 4 messages for GPT context (memory plugin provides longer-term context)
    messages = messages[-4:]
    
    # (1) Retrieve top memories and inject as context
    user_message = messages[-1].get("content", "") if messages else ""
    if user_message:
        try:
            memory_results = executor.run_tool("memory_search", {"query": user_message, "limit": 5}, {})
            if memory_results and isinstance(memory_results, dict) and memory_results.get("results"):
                relevant_memories = []
                for result in memory_results["results"]:
                    if result.get("score", 0) > 0.35:  # Threshold for relevance
                        relevant_memories.append(result["text"])
                
                if relevant_memories:
                    memory_context = "Relevant memories:\n" + "\n".join([f"- {mem}" for mem in relevant_memories])
                    # Inject memory context into system message or create new context message
                    if messages and messages[0].get("role") == "system":
                        messages[0]["content"] += "\n\n" + memory_context
                    else:
                        messages.insert(0, {"role": "system", "content": memory_context})
        except Exception as e:
            print(f"Memory retrieval error: {e}")
    
    # Insert system message to encourage KG and rules usage
    messages.insert(0, {"role": "system", "content": "Use KG and rules when helpful; always cite evidence if you used them."})
    
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
    
    # (2) Auto-save salient facts after computing response
    try:
        if user_message and final_response.get("content"):
            conversation_context = f"User said: {user_message}\nFriday replied: {final_response['content']}"
            executor.run_tool("memory_save", {"text": conversation_context}, {})
    except Exception as e:
        print(f"Memory save error: {e}")
    
    # (3) Write to daily journal (Quantum Mirror)
    try:
        if user_message and final_response.get("content"):
            executor.run_tool("journal_write", {
                "user_message": user_message,
                "friday_response": final_response["content"],
                "tool_used": final_response.get("tool_used")
            }, {})
    except Exception as e:
        print(f"Journal write error: {e}")
    
    return final_response

@app.post("/api/chat")
def chat_alias(req: ChatRequest):
    # Route alias to support clients calling /api/chat
    return chat(req)

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
