import os
import json
import pytest
from unittest.mock import MagicMock, patch
from subtitlekit.ui.desktop import I18n

def test_i18n_translation(tmp_path):
    # Setup mock locale file
    locale_dir = tmp_path / "locales"
    locale_dir.mkdir()
    en_json = locale_dir / "en.json"
    en_json.write_text(json.dumps({
        "test_key": "Test Value",
        "greet": "Hello {name}"
    }))
    
    with patch('subtitlekit.ui.desktop.Path') as mock_path:
        # Mock Path(__file__).parent / 'locales' to return our real tmp_path / "locales"
        mock_path.return_value.parent.__truediv__.return_value = locale_dir
        
        i18n = I18n('en')
        
        assert i18n.t("test_key") == "Test Value"
        assert i18n.t("greet", name="World") == "Hello World"
        assert i18n.t("missing") == "missing"

def test_config_set_and_get():
    from subtitlekit.optimizer.config import set_setting, get_setting
    
    try:
        set_setting("ui_test_key", "ui_value")
        assert get_setting("ui_test_key") == "ui_value"
    finally:
        set_setting("ui_test_key", None)

@patch('pysrt.open')
def test_optimize_logic_trigger(mock_srt):
    # This just ensures we can import and instantiate smoothly
    from subtitlekit.optimizer import OptimizerPipeline, OptimizationOptions
    
    mock_srt.return_value = MagicMock()
    
    options = OptimizationOptions(line_reduction=True)
    pipeline = OptimizerPipeline(options)
    
    assert pipeline.options == options
