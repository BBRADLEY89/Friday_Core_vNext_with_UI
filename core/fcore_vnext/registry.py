import os
import importlib.util
from typing import Dict, Any, List

class Registry:
    """Tool registry for loading and executing tools from plugins."""
    
    def __init__(self, plugins_root: str = "plugins"):
        self.plugins_root = plugins_root
        self.tools = {}
        
    def load(self):
        """Load all tools from plugins directory."""
        if not os.path.exists(self.plugins_root):
            return
            
        for plugin_dir in os.listdir(self.plugins_root):
            plugin_path = os.path.join(self.plugins_root, plugin_dir)
            if not os.path.isdir(plugin_path):
                continue
                
            tool_file = os.path.join(plugin_path, "tool.py")
            if not os.path.exists(tool_file):
                continue
                
            try:
                # Load the plugin module
                spec = importlib.util.spec_from_file_location(f"{plugin_dir}.tool", tool_file)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                # Get tools from module - support both TOOLS dict and get_tools/run_tool pattern
                if hasattr(module, 'TOOLS'):
                    for tool_name, tool_func in module.TOOLS.items():
                        self.tools[tool_name] = tool_func
                elif hasattr(module, 'get_tools') and hasattr(module, 'run_tool'):
                    # New plugin format with get_tools() and run_tool()
                    tools_list = module.get_tools()
                    for tool_info in tools_list:
                        tool_name = tool_info['name']
                        # Create wrapper function that calls run_tool
                        def make_tool_func(module_ref, name):
                            return lambda args, ctx={}: module_ref.run_tool(name, args, ctx)
                        self.tools[tool_name] = make_tool_func(module, tool_name)
                        
            except Exception as e:
                print(f"Failed to load plugin {plugin_dir}: {e}")
                
        # Add built-in tools
        self._add_builtin_tools()
        
    def _add_builtin_tools(self):
        """Add built-in file operations."""
        def file_read(args):
            path = args.get("path", "")
            try:
                with open(path, 'r') as f:
                    return {"content": f.read()}
            except Exception as e:
                return {"error": str(e)}
                
        def file_write(args):
            path = args.get("path", "")
            content = args.get("content", "")
            try:
                # Create directory if it doesn't exist
                os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
                with open(path, 'w') as f:
                    f.write(content)
                return {"success": True, "path": path}
            except Exception as e:
                return {"error": str(e)}
                
        self.tools["file_read"] = file_read
        self.tools["file_write"] = file_write
        
    def list_tools(self) -> List[Dict[str, str]]:
        """Return list of available tools."""
        return [{"name": name} for name in self.tools.keys()]
        
    def run(self, tool_name: str, args: Dict[str, Any], context: Dict[str, Any] = None) -> Any:
        """Execute a tool with given arguments."""
        if tool_name not in self.tools:
            return {"error": f"Tool '{tool_name}' not found"}
            
        try:
            return self.tools[tool_name](args)
        except Exception as e:
            return {"error": f"Tool execution failed: {str(e)}"}