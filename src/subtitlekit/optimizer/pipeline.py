from typing import List, Optional
import pysrt
import logging

from .options import OptimizationOptions
from .line_reducer import reduce_lines
from .cps_optimizer import optimize_cps
from .interjection_remover import InterjectionRemover
from .llm_shortener import find_high_cps_segments, shorten_with_llm

logger = logging.getLogger(__name__)

class OptimizerPipeline:
    """
    Orchestrates the subtitle optimization phases.
    """
    
    def __init__(self, options: Optional[OptimizationOptions] = None):
        self.options = options or OptimizationOptions()
        self.interjection_remover = InterjectionRemover(self.options.lang)
    
    def run(self, subtitles: pysrt.SubRipFile) -> pysrt.SubRipFile:
        """
        Run the enabled optimization phases on the provided subtitles.
        """
        if not subtitles:
            return subtitles
            
        current_subs = subtitles
        
        # 1. Interjection Removal
        if self.options.interjection_removal:
            logger.info(f"Running interjection removal for lang: {self.options.lang}")
            processed = self.interjection_remover.process(current_subs)
            current_subs = pysrt.SubRipFile(processed)
            
        # 2. Line Reduction
        if self.options.line_reduction:
            logger.info(f"Running line reduction (max {self.options.max_lines})")
            for sub in current_subs:
                reduce_lines(sub, self.options.max_lines)
                
        # 3. CPS Optimization (Timing & Merging)
        if self.options.cps_optimization:
            logger.info(f"Running CPS optimization (target: {self.options.cps_target})")
            processed = optimize_cps(current_subs, self.options)
            current_subs = pysrt.SubRipFile(processed)
            
        # 4. LLM Shortening
        if self.options.llm_shortening:
            logger.info(f"Running LLM shortening (model: {self.options.model})")
            segments = find_high_cps_segments(current_subs, self.options)
            if segments:
                logger.info(f"Found {len(segments)} segments needing LLM shortening")
                shortened_segments = shorten_with_llm(segments, self.options)
                
                # Apply shortened text back to subtitles
                seg_map = {seg.index: seg.shortened_text for seg in shortened_segments if seg.shortened_text}
                for sub in current_subs:
                    if sub.index in seg_map:
                        sub.text = seg_map[sub.index]
            else:
                logger.info("No segments found needing LLM shortening")
                
        return current_subs
