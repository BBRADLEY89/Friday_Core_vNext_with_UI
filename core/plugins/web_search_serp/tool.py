import os, requests
from typing import List, Dict, Any

def get_tools() -> List[Dict[str, Any]]:
    return [
        {"name":"web_search","description":"SerpAPI web search",
         "parameters":{"type":"object","properties":{"query":{"type":"string"},"num":{"type":"integer","default":5}},"required":["query"]}}
    ]

def run_tool(name: str, args: dict, ctx: dict) -> Dict[str, Any]:
    if name != "web_search": raise ValueError("Unknown tool")
    key = os.getenv("SERPAPI_API_KEY") or ctx.get("serpapi_key") or ""
    if not key:
        return {"results":[{"title":"SerpAPI key missing","snippet":"Set SERPAPI_API_KEY or config.web.serpapi_api_key"}]}
    q = args["query"]; num = int(args.get("num",5))
    r = requests.get("https://serpapi.com/search.json",
                     params={"engine":"google","q":q,"num":num,"api_key":key}, timeout=30)
    r.raise_for_status()
    data = r.json()
    out = []
    for item in (data.get("organic_results") or [])[:num]:
        out.append({"title": item.get("title"), "snippet": item.get("snippet")})
    return {"results": out or [{"title":"No results","snippet":"(empty)"}]}
