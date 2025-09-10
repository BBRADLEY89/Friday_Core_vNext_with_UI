from typing import List, Dict, Any
import json

def tools_manifest(registry) -> str:
    """Build a compact, human-readable capability manifest for the system prompt."""
    items = []
    for t in registry.list_tools():
        name = t.get("name")
        desc = t.get("description", "")
        plugin = t.get("plugin", "")
        items.append({"name": name, "plugin": plugin, "desc": desc})
    return json.dumps(items, ensure_ascii=False)