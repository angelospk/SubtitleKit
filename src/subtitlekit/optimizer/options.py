from dataclasses import dataclass, field
from typing import Optional

@dataclass
class OptimizationOptions:
    """Settings for the subtitle optimization pipeline."""
    # Phase flags
    line_reduction: bool = False
    cps_optimization: bool = False
    interjection_removal: bool = False
    llm_shortening: bool = False
    simplify: bool = False  # Experimental translation prep (selective)

    # Core parameters
    lang: str = "en"
    cps_target: float = 20.0
    max_chars: int = 90
    max_lines: int = 2
    max_duration: float = 7.0
    min_duration: float = 0.833  # 5/6 second
    min_gap: float = 0.12  # Minimum gap between subtitles

    # LLM settings
    api_key: Optional[str] = None
    model: str = "gemini-2.0-flash"
