"""Pluggable, headless LLM backends.

Primary: OpenCode CLI with a free model (`opencode run --format json`).
Fallback: Gemini CLI. Tests use ``MockBackend``; nothing here is called by
the test-suite with a real process (the process runner is injectable).
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Union

log = logging.getLogger(__name__)

Runner = Callable[[List[str], str, float], "subprocess.CompletedProcess[str]"]


class LLMError(RuntimeError):
    pass


def _run(argv: List[str], cwd: str, timeout: float) -> "subprocess.CompletedProcess[str]":
    return subprocess.run(
        argv, cwd=cwd, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL
    )


class LLMBackend:
    name = "base"

    def complete(self, prompt: str) -> str:  # pragma: no cover - interface
        raise NotImplementedError


@dataclass
class OpenCodeBackend(LLMBackend):
    model: str = "opencode/big-pickle"
    binary: str = "opencode"
    timeout: float = 300.0
    runner: Runner = field(default=_run, repr=False)
    name: str = "opencode"

    def complete(self, prompt: str) -> str:
        argv = [self.binary, "run", "--format", "json", "-m", self.model, prompt]
        # Empty working dir: the OpenCode agent must not see project files.
        with tempfile.TemporaryDirectory(prefix="subtitlekit-llm-") as cwd:
            try:
                proc = self.runner(argv, cwd, self.timeout)
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise LLMError(f"opencode failed to run: {exc}") from exc
        if proc.returncode != 0:
            raise LLMError(f"opencode exit {proc.returncode}: {proc.stderr[-300:]}")
        text = parse_opencode_json(proc.stdout)
        if not text.strip():
            raise LLMError("opencode returned no text")
        return text


def parse_opencode_json(stdout: str) -> str:
    """Join the ``text`` parts of ``opencode run --format json`` output."""
    parts: List[str] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "error":
            raise LLMError(f"opencode error event: {str(event)[:300]}")
        part = event.get("part") or {}
        if event.get("type") == "text" and isinstance(part.get("text"), str):
            parts.append(part["text"])
    return "".join(parts)


@dataclass
class GeminiCliBackend(LLMBackend):
    model: Optional[str] = None
    binary: str = "gemini"
    timeout: float = 300.0
    runner: Runner = field(default=_run, repr=False)
    name: str = "gemini"

    def complete(self, prompt: str) -> str:
        argv = [self.binary, "--skip-trust"]
        if self.model:
            argv += ["--model", self.model]
        argv += ["-p", prompt]
        with tempfile.TemporaryDirectory(prefix="subtitlekit-llm-") as cwd:
            try:
                proc = self.runner(argv, cwd, self.timeout)
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise LLMError(f"gemini failed to run: {exc}") from exc
        if proc.returncode != 0 or not proc.stdout.strip():
            raise LLMError(f"gemini exit {proc.returncode}: {proc.stderr[-300:]}")
        return proc.stdout


@dataclass
class MockBackend(LLMBackend):
    """Scripted backend for tests: a list of replies or a function of the prompt."""

    replies: Union[Sequence[str], Callable[[str], str]] = ()
    prompts: List[str] = field(default_factory=list)
    name: str = "mock"

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if callable(self.replies):
            return self.replies(prompt)
        if len(self.prompts) > len(self.replies):
            raise LLMError("mock backend has no more replies")
        return self.replies[len(self.prompts) - 1]


@dataclass
class FallbackBackend(LLMBackend):
    backends: Sequence[LLMBackend] = ()
    name: str = "fallback"

    def complete(self, prompt: str) -> str:
        errors = []
        for backend in self.backends:
            try:
                return backend.complete(prompt)
            except LLMError as exc:
                log.warning("LLM backend %s failed: %s", backend.name, exc)
                errors.append(f"{backend.name}: {exc}")
        raise LLMError("all LLM backends failed: " + "; ".join(errors))


@dataclass
class CachingBackend(LLMBackend):
    """Disk cache of successful replies, keyed by backend name + model + prompt.

    Re-running a film after changing thresholds then costs no LLM time.
    Failures are never cached.
    """

    inner: LLMBackend = None
    cache_dir: str = "~/.cache/subtitlekit/llm"
    hits: int = 0

    @property
    def name(self) -> str:  # type: ignore[override]
        return self.inner.name

    def _path(self, prompt: str) -> str:
        import hashlib
        import os

        key = f"{self.inner.name}|{getattr(self.inner, 'model', '')}|{prompt}"
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return os.path.join(os.path.expanduser(self.cache_dir), digest[:2], digest + ".txt")

    def complete(self, prompt: str) -> str:
        import os

        path = self._path(prompt)
        try:
            with open(path, encoding="utf-8") as fh:
                reply = fh.read()
            self.hits += 1
            return reply
        except OSError:
            pass
        reply = self.inner.complete(prompt)
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(reply)
            os.replace(tmp, path)
        except OSError as exc:  # a cache problem must never fail the call
            log.warning("LLM cache write failed: %s", exc)
        return reply

    def forget(self, prompt: str) -> None:
        """Drop a cached reply the caller rejected, so a rerun asks again."""
        import os

        try:
            os.remove(self._path(prompt))
        except OSError:
            pass


def forget(backend: LLMBackend, prompt: str) -> None:
    """Evict a rejected reply from a caching backend (no-op otherwise)."""
    fn = getattr(backend, "forget", None)
    if callable(fn):
        fn(prompt)


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extract_json(text: str) -> Any:
    """Parse the first JSON object/array in an LLM reply (fences tolerated)."""
    candidates = [m.group(1) for m in _FENCE_RE.finditer(text)] + [text]
    for chunk in candidates:
        chunk = chunk.strip()
        try:
            return json.loads(chunk)
        except json.JSONDecodeError:
            pass
        for opener, closer in (("{", "}"), ("[", "]")):
            start, end = chunk.find(opener), chunk.rfind(closer)
            if 0 <= start < end:
                try:
                    return json.loads(chunk[start : end + 1])
                except json.JSONDecodeError:
                    continue
    raise LLMError(f"no JSON in reply: {text[:200]!r}")


def make_backend(cfg: Optional[Dict[str, Any]] = None) -> LLMBackend:
    """Build a backend from the ``llm`` section of the pipeline config."""
    cfg = cfg or {}
    backend = _make_uncached(cfg)
    if cfg.get("cache_dir") and backend.name != "mock":
        return CachingBackend(inner=backend, cache_dir=cfg["cache_dir"])
    return backend


def _make_uncached(cfg: Dict[str, Any]) -> LLMBackend:
    kind = cfg.get("backend", "opencode")
    timeout = float(cfg.get("timeout_s", 300))
    opencode = OpenCodeBackend(model=cfg.get("model", "opencode/big-pickle"), timeout=timeout)
    gemini = GeminiCliBackend(model=cfg.get("gemini_model"), timeout=timeout)
    if kind == "opencode":
        return opencode
    if kind == "gemini":
        return gemini
    if kind == "fallback":
        return FallbackBackend([opencode, gemini])
    if kind == "mock":
        return MockBackend(replies=lambda prompt: "{}")
    raise ValueError(f"unknown llm backend: {kind}")
