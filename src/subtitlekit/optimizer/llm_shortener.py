import json
import logging
from dataclasses import dataclass
from typing import List, Optional
import pysrt

from ..tools.reading_speed import calculate_cps
from .options import OptimizationOptions

logger = logging.getLogger(__name__)

@dataclass
class HighCPSSegment:
    """A subtitle segment that needs LLM shortening."""
    index: int
    original_text: str
    current_cps: float
    target_cps: float
    chars_to_reduce: int
    context_before: str = ""
    context_after: str = ""
    next_is_uppercase: bool = True
    shortened_text: Optional[str] = None

def find_high_cps_segments(
    subtitles: pysrt.SubRipFile,
    options: OptimizationOptions,
    min_reduction: int = 6
) -> List[HighCPSSegment]:
    """Find subtitle segments that need LLM shortening."""
    segments = []

    for i, sub in enumerate(subtitles):
        duration = (sub.end.ordinal - sub.start.ordinal) / 1000.0
        cps = calculate_cps(sub.text, duration)

        if cps <= options.cps_target or cps == float('inf'):
            continue

        # Calculate how many chars need to be reduced
        current_chars = len(sub.text) # Should we use stripped? pysrt does some of it
        target_chars = int(options.cps_target * duration)
        chars_to_reduce = current_chars - target_chars

        if chars_to_reduce < min_reduction:
            continue

        # Get context
        context_before = subtitles[i - 1].text if i > 0 else ""
        context_after = subtitles[i + 1].text if i + 1 < len(subtitles) else ""

        # Determine if next text starts with uppercase (for punctuation rule)
        next_is_uppercase = True
        if context_after:
            for char in context_after:
                if char.isalpha():
                    next_is_uppercase = char.isupper()
                    break

        segment = HighCPSSegment(
            index=sub.index,
            original_text=sub.text,
            current_cps=cps,
            target_cps=options.cps_target,
            chars_to_reduce=chars_to_reduce,
            context_before=context_before,
            context_after=context_after,
            next_is_uppercase=next_is_uppercase,
        )
        segments.append(segment)

    return segments

def build_shortening_prompt(segments: List[HighCPSSegment], simplify: bool = False) -> str:
    """Build a prompt for Gemini API to shorten segments."""
    base_rules = """You are a professional subtitle editor. Shorten the following subtitle texts to meet character limits while keeping the meaning intact.

Rules:
1. Keep the core meaning intact
2. Remove unnecessary words (very, really, just, etc.)
3. Use shorter synonyms
4. Keep natural speech flow
5. TRAILING PUNCTUATION RULE: Do NOT end with "." unless next_is_uppercase is true
6. Return ONLY valid JSON array with objects having "index" and "text" keys
"""
    if simplify:
        base_rules += "7. SIMPLIFICATION RULE: Use simpler vocabulary and sentence structure to make the subtitles easier to translate.\n"

    prompt = base_rules + "\nSegments to shorten:\n"

    for seg in segments:
        char_count = len(seg.original_text.replace('\n', '').replace('\r', ''))
        context_before = seg.context_before[:50] + "..." if seg.context_before else "(start)"
        context_after = seg.context_after[:50] + "..." if seg.context_after else "(end)"
        prompt += f"""
---
Index: {seg.index}
Original ({char_count} chars, need to reduce by {seg.chars_to_reduce}): "{seg.original_text}"
Context before: "{context_before}"
Context after: "{context_after}"
next_is_uppercase: {seg.next_is_uppercase}
---
"""

    prompt += "\nReturn JSON array like: [{\"index\": 1, \"text\": \"shortened text\"}, ...]\n"
    return prompt

def shorten_with_llm(
    segments: List[HighCPSSegment],
    options: OptimizationOptions
) -> List[HighCPSSegment]:
    """Call Gemini API to shorten segments."""
    if not segments:
        return []

    if not options.api_key:
        logger.error("Gemini API key is required for LLM shortening.")
        return segments

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        logger.error("google-genai package required for LLM shortening. Install with: pip install google-genai")
        return segments

    client = genai.Client(api_key=options.api_key)
    prompt = build_shortening_prompt(segments, options.simplify)

    try:
        response = client.models.generate_content(
            model=options.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            )
        )

        if not response.text:
            return segments

        # Clean response if it contains markdown markers
        cleaned_text = response.text.strip()
        if cleaned_text.startswith("```json"):
            cleaned_text = cleaned_text[7:]
        if cleaned_text.endswith("```"):
            cleaned_text = cleaned_text[:-3]
        
        results = json.loads(cleaned_text.strip())
        
        # Map results back to segments
        idx_to_text = {item['index']: item['text'] for item in results if 'index' in item and 'text' in item}
        
        for seg in segments:
            if seg.index in idx_to_text:
                seg.shortened_text = idx_to_text[seg.index]
                
        return segments
    except Exception as e:
        logger.error(f"Error during LLM shortening: {str(e)}")
        return segments
