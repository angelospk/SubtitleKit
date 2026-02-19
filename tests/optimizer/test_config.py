import os
import json
import pytest
from pathlib import Path
from subtitlekit.optimizer.config import load_config, save_config, get_setting, set_setting

def test_config_save_load(tmp_path, monkeypatch):
    # Mock CONFIG_DIR and CONFIG_FILE
    config_dir = tmp_path / ".subtitlekit"
    config_file = config_dir / "config.json"
    
    monkeypatch.setattr("subtitlekit.optimizer.config.CONFIG_DIR", config_dir)
    monkeypatch.setattr("subtitlekit.optimizer.config.CONFIG_FILE", config_file)
    
    test_data = {"api_key": "test_key", "target_cps": 20.0}
    save_config(test_data)
    
    loaded = load_config()
    assert loaded == test_data
    assert loaded["api_key"] == "test_key"

def test_get_set_setting(tmp_path, monkeypatch):
    config_dir = tmp_path / ".subtitlekit"
    config_file = config_dir / "config.json"
    
    monkeypatch.setattr("subtitlekit.optimizer.config.CONFIG_DIR", config_dir)
    monkeypatch.setattr("subtitlekit.optimizer.config.CONFIG_FILE", config_file)
    
    set_setting("model", "gemini-pro")
    assert get_setting("model") == "gemini-pro"
    assert get_setting("none", "default") == "default"
