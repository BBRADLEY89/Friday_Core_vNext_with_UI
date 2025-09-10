# Executor module for tool execution
from .registry import Registry

class Executor:
    def __init__(self, registry: Registry):
        self.registry = registry
        
    def run_tool(self, tool_name: str, arguments: dict, context: dict = None):
        """Execute a tool with given arguments"""
        try:
            # Handle web_search separately (same logic as in server.py)
            if tool_name == "web_search":
                from serpapi import GoogleSearch
                import os
                import toml
                
                # Load config
                config_path = "config/settings.toml"
                config = toml.load(config_path) if os.path.isfile(config_path) else {}
                
                query = arguments.get("query", "")
                num = arguments.get("num", 3)
                
                # Check if API key is configured
                api_key = context.get("serpapi_key") or os.environ.get("SERPAPI_API_KEY") or config.get("web", {}).get("serpapi_api_key", "")
                if not api_key:
                    # Return stub data if no API key
                    return {
                        "results": [
                            {
                                "title": f"Stub result {i+1} for: {query}", 
                                "snippet": f"This is a stub search result for '{query}'. Configure SerpAPI key to get real results.",
                                "link": f"https://example.com/{i+1}"
                            }
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
            
            # Use registry for other tools
            return self.registry.run(tool_name, arguments)
            
        except Exception as e:
            return {"error": f"Tool execution failed: {str(e)}"}