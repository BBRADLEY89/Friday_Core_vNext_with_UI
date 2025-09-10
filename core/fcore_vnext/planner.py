from typing import List, Dict, Any
from .registry import Registry
from .sandbox import Sandbox
from .adapters import openai_adapter
from .openai_capabilities import tools_manifest

REFUSAL_HINTS = [
    "i can't", "i can't", "i am unable", "i'm unable", "i am not able",
    "i don't have the ability", "as an ai", "i cannot"
]

class Planner:
    def __init__(self, registry: Registry, sandbox: Sandbox, api_key: str = ""):
        self.registry = registry
        self.sandbox = sandbox
        self.api_key = api_key

    def _capabilities(self) -> str:
        return tools_manifest(self.registry)

    def step(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        # First attempt
        out = openai_adapter.generate(messages, self.registry.list_tools(), self._capabilities(), api_key=self.api_key)

        # Refusal interceptor: if model says "I can't" but a tool exists that matches the intent,
        # append a coaching system hint and try once more.
        content = (out.get("content") or "").lower()
        if content and any(h in content for h in REFUSAL_HINTS):
            # Coach it to use tools rather than refusing.
            messages2 = [{"role":"system","content":
                "Reminder: You have the above live capabilities; if a requested task is achievable with available tools, call the tool or propose a plan. Do not give a generic refusal."
            }] + messages
            out = openai_adapter.generate(messages2, self.registry.list_tools(), self._capabilities(), api_key=self.api_key)

        return out