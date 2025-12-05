"""
SubtitleKit UI Module
"""

try:
    from .colab import show_ui
    __all__ = ['show_ui']
except ImportError:
    # ipywidgets not installed - colab UI not available
    __all__ = []

