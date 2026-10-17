"""Film context: the published plot of the film or episode, so the translator knows the story and tone.

Harold's practice: paste the Wikipedia plot into the prompt. Here one LLM call with web search finds it
(Wikipedia first), or a hand-written ``plot.md`` in the film folder replaces the search. The plot comes from
the web, so prompts carry it as JSON data, never as prompt text.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple
from urllib.parse import urlparse

from .llm import LLMBackend, LLMError, extract_json, forget

PLOT_FILE = "plot.md"

PLOT_PROMPT = """You find the published plot of one film or TV episode for a subtitle translator who needs its story and tone.
Search the web: Wikipedia first, then TMDB, IMDb or the broadcaster. Use only a page about this exact film or episode
(same title, year, season and episode). Never invent or guess a plot.
Return ONLY a JSON object, no commentary:
{{"found": true, "source_url": "<URL of the page you used>", "summary": "<2-3 sentences: genre, tone, setting>",
"plot": "<the plot in English, at most {words} words>"}}
If you cannot find this exact film or episode, return {{"found": false}}.
Film (JSON data):
{film}"""


@dataclass
class FilmContext:
    text: str
    origin: str  # "llm" (web search) or "file" (plot.md in the film folder)
    source_url: str = ""

    def to_markdown(self) -> str:
        head = f"Source: {self.source_url}\n\n" if self.source_url else ""
        return head + self.text + "\n"


def _cut(text: str, max_chars: int) -> Tuple[str, List[str]]:
    if len(text) <= max_chars:
        return text, []
    cut = text[:max_chars]
    stop = cut.rfind(". ")
    cut = cut[: stop + 1] if stop > max_chars // 2 else cut.rstrip()
    return cut, [f"film_context: plot cut to {max_chars} chars"]


def _reject(data: Any) -> str:
    if not isinstance(data, dict) or data.get("found") is not True:
        return "plot not found"
    url = data.get("source_url")
    try:
        parsed = urlparse(url.strip()) if isinstance(url, str) else None
        host = parsed.hostname if parsed is not None else None
    except ValueError:  # e.g. "https://[" (bad IPv6 literal)
        parsed, host = None, None
    if parsed is None or parsed.scheme not in ("http", "https") or not host:
        return "no http(s) source_url"
    plot = data.get("plot")
    if not isinstance(plot, str) or not plot.strip():
        return "empty plot"
    return ""


def fetch_plot(
    meta: Any, backend: LLMBackend, max_chars: int = 6000, release: str = "", folder: str = "",
) -> Tuple[Optional[FilmContext], List[str]]:
    # The release and folder names keep the episode (S03E01) when the title does not.
    film = {k: v for k, v in {
        "title": getattr(meta, "title", ""), "year": getattr(meta, "year", None),
        "imdb_id": getattr(meta, "imdb_id", ""), "release": release, "folder": folder,
        "synopsis": getattr(meta, "synopsis", ""),
    }.items() if v}
    prompt = PLOT_PROMPT.format(words=max(50, max_chars // 7), film=json.dumps(film, ensure_ascii=False))
    try:
        data = extract_json(backend.complete(prompt))
    except LLMError as exc:
        forget(backend, prompt)
        return None, [f"film_context: {exc}"]
    problem = _reject(data)
    if problem:
        forget(backend, prompt)  # a rerun must search again, not replay the rejected reply
        return None, [f"film_context: {problem}"]
    url, summary, plot = data["source_url"].strip(), data.get("summary"), data["plot"]
    parts = [s.strip() for s in (summary if isinstance(summary, str) else "", plot) if s.strip()]
    text, problems = _cut("\n\n".join(parts), max_chars)
    return FilmContext(text, "llm", url), problems


def load_plot(film_dir: str, max_chars: int = 6000) -> Tuple[Optional[FilmContext], List[str]]:
    """A hand-written plot.md in the film folder wins over the web search."""
    path = os.path.join(film_dir, PLOT_FILE)
    if not os.path.isfile(path):
        return None, []
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read().strip()
    except (OSError, UnicodeDecodeError) as exc:
        return None, [f"film_context: {PLOT_FILE} unreadable: {exc}"[:200]]
    return (FilmContext(_cut(text, max_chars)[0], "file"), []) if text else (None, [])
