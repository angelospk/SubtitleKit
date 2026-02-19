import os
import re
from typing import List, Optional
import pysrt

class InterjectionRemover:
    """
    Remove interjection words from subtitle text.
    Generalized to support multiple languages via external word lists.
    """
    
    def __init__(self, lang: str = "en"):
        self.lang = lang
        self.interjections = self._load_interjections(lang)
    
    def _load_interjections(self, lang: str) -> List[str]:
        """Load interjections for the specified language."""
        base_dir = os.path.dirname(__file__)
        list_path = os.path.join(base_dir, "interjections", f"{lang}.txt")
        
        if not os.path.exists(list_path):
            # Fallback to English or just Return empty if not found
            # The design says log warning and skip
            return []
            
        try:
            with open(list_path, "r", encoding="utf-8") as f:
                return [line.strip() for line in f if line.strip() and not line.startswith("#")]
        except Exception:
            return []

    def remove_interjections(self, text: str) -> str:
        """Remove interjections from the given text."""
        if not text or not self.interjections:
            return text
            
        result = text
        # Simple whole-word replacement for each interjection
        for s in self.interjections:
            # Word boundary check - handle punctuation
            pattern = r'\b' + re.escape(s) + r'\b'
            result = re.sub(pattern, '', result, flags=re.IGNORECASE)
        
        # Cleanup extra spaces left behind
        result = re.sub(r' +', ' ', result).strip()
        # Handle cases like " , " or beginning of line ", "
        result = re.sub(r'^, ', '', result)
        result = re.sub(r' ,', ',', result)
        
        return result

    def process(self, subtitles: pysrt.SubRipFile) -> List[pysrt.SubRipItem]:
        """Apply interjection removal to all subtitles."""
        if not self.interjections:
            return list(subtitles)
            
        for sub in subtitles:
            sub.text = self.remove_interjections(sub.text)
            
        # Filter out subtitles that became empty
        return [sub for sub in subtitles if sub.text.strip()]
