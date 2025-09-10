import os
import pathlib
from datetime import datetime
from zoneinfo import ZoneInfo
import toml

def get_config_value(section, key, env_var_name):
    """Get config value, preferring environment variable over config file"""
    env_value = os.environ.get(env_var_name)
    if env_value:
        return env_value
    
    # Load config
    config_path = "config/settings.toml"
    config = toml.load(config_path) if os.path.isfile(config_path) else {}
    return config.get(section, {}).get(key, "UTC")

def journal_write(args):
    """Write conversation entry to daily journal (Quantum Mirror)"""
    user_message = args.get("user_message", "")
    friday_response = args.get("friday_response", "")
    tool_used = args.get("tool_used")
    try:
        # Get timezone from config
        tz = get_config_value("timezone", "tz", "TZ_OVERRIDE") or "UTC"
        now = datetime.now(ZoneInfo(tz))
        
        # Create journal directory structure
        journal_dir = pathlib.Path("memory/journal")
        journal_dir.mkdir(parents=True, exist_ok=True)
        
        # Daily journal file format: YYYY-MM-DD.md
        journal_file = journal_dir / f"{now.strftime('%Y-%m-%d')}.md"
        
        # Format entry
        timestamp = now.strftime("%H:%M")
        entry = f"\n## {timestamp}\n\n**User:** {user_message}\n\n**Friday:** {friday_response}\n"
        if tool_used:
            entry += f"\n*[Used tool: {tool_used}]*\n"
        entry += "\n---\n"
        
        # Append to journal file
        with open(journal_file, "a", encoding="utf-8") as f:
            # Add header if new file
            if journal_file.stat().st_size == 0:
                f.write(f"# Journal - {now.strftime('%A, %B %d, %Y')}\n\n")
            f.write(entry)
        
        return {
            "status": "success", 
            "file": str(journal_file),
            "timestamp": now.isoformat()
        }
        
    except Exception as e:
        return {"status": "error", "message": str(e)}

# Export tools
TOOLS = {
    "journal_write": journal_write
}