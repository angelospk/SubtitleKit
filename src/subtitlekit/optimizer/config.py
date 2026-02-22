import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

CONFIG_DIR = Path.home() / ".subtitlekit"
CONFIG_FILE = CONFIG_DIR / "config.json"

def ensure_config_dir():
    """Ensure the config directory exists with safe permissions."""
    if not CONFIG_DIR.exists():
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_DIR.chmod(0o700)

def load_config() -> Dict[str, Any]:
    """Load configuration from the config file."""
    if not CONFIG_FILE.exists():
        return {}
    
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}

def save_config(config: Dict[str, Any]):
    """Save configuration to the config file with safe permissions."""
    ensure_config_dir()
    
    try:
        import tempfile
        fd, temp_path = tempfile.mkstemp(dir=CONFIG_DIR, prefix='config_tmp', suffix='.json', text=True)
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(config, f, indent=4)
            os.chmod(temp_path, 0o600)
            os.replace(temp_path, CONFIG_FILE)
        except Exception:
            os.unlink(temp_path)
            raise
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Failed to save config: {e}")

def get_setting(key: str, default: Any = None) -> Any:
    """Get a specific setting from the config."""
    config = load_config()
    return config.get(key, default)

def set_setting(key: str, value: Any):
    """Set a specific setting in the config."""
    config = load_config()
    config[key] = value
    save_config(config)

def get_secret(key: str) -> Optional[str]:
    """Alias for get_setting, specifically for secrets like API keys."""
    return get_setting(key)

def set_secret(key: str, value: str):
    """Alias for set_setting, specifically for secrets."""
    set_setting(key, value)
