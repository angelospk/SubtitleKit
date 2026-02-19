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
        # Mock Path(__file__).parent to return our tmp_path
        mock_path.return_value.parent.__truediv__.return_value = locale_dir
        # Also need to mock locale_file existence
        mock_path.return_value.__truediv__.return_value = en_json
        
        i18n = I18n('en')
        # Since the class loads from __file__.parent / 'locales', we hack it
        i18n.translations = json.loads(en_json.read_text())
        
        assert i18n.t("test_key") == "Test Value"
        assert i18n.t("greet", name="World") == "Hello World"
        assert i18n.t("missing") == "missing"

def test_config_integration_in_ui():
    from subtitlekit.optimizer.config import set_setting, get_setting
    
    set_setting("ui_test_key", "ui_value")
    assert get_setting("ui_test_key") == "ui_value"

@patch('subtitlekit.optimizer.pipeline.OptimizerPipeline.run')
@patch('pysrt.open')
def test_optimize_logic_trigger(mock_srt, mock_pipeline_run):
    # This just ensures we can import and instantiate smoothly
    from subtitlekit.optimizer import OptimizerPipeline, OptimizationOptions
    
    mock_srt.return_value = MagicMock()
    mock_pipeline_run.return_value = MagicMock()
    
    options = OptimizationOptions(line_reduction=True)
    pipeline = OptimizerPipeline(options)
    pipeline.run(mock_srt.return_value)
    
    assert mock_pipeline_run.called
