"""Pluggable, headless LLM backends.

Primary: OpenCode CLI with a free model (`opencode run --format json`).
Fallback: Gemini CLI. Also Claude Code CLI in headless mode (`claude -p`).
Tests use ``MockBackend``; nothing here is called by
the test-suite with a real process (the process runner is injectable).
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Union

log = logging.getLogger(__name__)

Runner = Callable[[List[str], str, float], "subprocess.CompletedProcess[str]"]
InputRunner = Callable[[List[str], str, float, str], "subprocess.CompletedProcess[str]"]


class LLMError(RuntimeError):
    pass


def _run(argv: List[str], cwd: str, timeout: float) -> "subprocess.CompletedProcess[str]":
    return subprocess.run(
        argv, cwd=cwd, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL
    )


def _run_input(
    argv: List[str], cwd: str, timeout: float, input_text: str
) -> "subprocess.CompletedProcess[str]":
    return subprocess.run(
        argv, cwd=cwd, input=input_text, capture_output=True, text=True, timeout=timeout
    )


class LLMBackend:
    name = "base"

    def complete(self, prompt: str) -> str:  # pragma: no cover - interface
        raise NotImplementedError


OPENCODE_CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "opencode_text.json")
OPENCODE_TEXT_ONLY = "Do not use any tools: answer directly in text.\n\n"


@dataclass
class OpenCodeBackend(LLMBackend):
    """`opencode run` on a private server with the text-only config (OPENCODE_CONFIG), in an empty temp dir.

    The free models refuse a request without the usual tools, so the config keeps every tool listed as
    "ask" (a non-interactive run rejects each one) and removes only "execute", which "ask" does not stop.
    """

    model: str = "opencode/big-pickle"
    binary: str = "opencode"
    timeout: float = 300.0
    runner: Runner = field(default=_run, repr=False)
    name: str = "opencode"

    def complete(self, prompt: str) -> str:
        # Empty working dir: the OpenCode agent must not see project files. Empty HOME and XDG_CONFIG_HOME: the
        # user's global config and ~/.opencode (agents, plugins, skills, MCP servers, allow rules) must not merge
        # into the text-only one. Data, cache and state stay the user's own (login, downloaded binaries).
        real = {"XDG_DATA_HOME": "~/.local/share", "XDG_CACHE_HOME": "~/.cache", "XDG_STATE_HOME": "~/.local/state"}
        keep = [f"{k}={os.environ.get(k) or os.path.expanduser(v)}" for k, v in real.items()]
        with tempfile.TemporaryDirectory(prefix="subtitlekit-llm-") as cwd, \
                tempfile.TemporaryDirectory(prefix="subtitlekit-oc-home-") as home:
            argv = ["env", "-u", "OPENCODE_CONFIG_CONTENT", "-u", "OPENCODE_CONFIG_DIR", f"HOME={home}",
                    f"XDG_CONFIG_HOME={os.path.join(home, '.config')}", *keep, f"OPENCODE_CONFIG={OPENCODE_CONFIG}",
                    self.binary, "run", "--standalone", "--agent", "build",
                    "--format", "json", "-m", self.model, "--", OPENCODE_TEXT_ONLY + prompt]
            try:
                proc = self.runner(argv, cwd, self.timeout)
            except subprocess.TimeoutExpired as exc:
                raise LLMError(f"opencode timed out after {self.timeout:.0f} s") from exc
            except OSError as exc:
                raise LLMError(f"opencode failed to run: {exc}") from exc
        text = parse_opencode_json(proc.stdout)  # raises on an "error" event (it is on stdout)
        if proc.returncode != 0:
            raise LLMError(f"opencode exit {proc.returncode}: {(proc.stderr or proc.stdout)[-300:]}")
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
            except subprocess.TimeoutExpired as exc:
                raise LLMError(f"gemini timed out after {self.timeout:.0f} s") from exc
            except OSError as exc:
                raise LLMError(f"gemini failed to run: {exc}") from exc
        if proc.returncode != 0 or not proc.stdout.strip():
            raise LLMError(f"gemini exit {proc.returncode}: {proc.stderr[-300:]}")
        return proc.stdout


CLAUDE_SYSTEM = (
    "You are a text-processing engine. Follow the user's instructions exactly "
    "and reply with the requested output only."
)


CLAUDE_TOOLS = ("", "WebSearch")


@dataclass
class ClaudeCliBackend(LLMBackend):
    """Claude Code CLI in headless mode (`claude -p`), e.g. Haiku 5.5. Prompt goes on stdin."""

    model: str = "claude-haiku-5-5"
    binary: str = "claude"
    timeout: float = 300.0
    effort: str = ""  # claude --effort (low, medium, high); "" = the CLI default
    tools: str = ""
    runner: InputRunner = field(default=_run_input, repr=False)
    name: str = "claude"

    def __post_init__(self) -> None:
        # Web search is the only tool a subtitle prompt may get: never shell or file access.
        if self.tools not in CLAUDE_TOOLS:
            raise ValueError(f"claude tools not allowed: {self.tools!r} (allowed: {', '.join(map(repr, CLAUDE_TOOLS))})")

    def complete(self, prompt: str) -> str:
        argv = [
            self.binary, "-p", "--model", self.model, "--output-format", "json",
            "--setting-sources", "", "--tools", self.tools, "--no-session-persistence",
            "--strict-mcp-config",
            "--system-prompt", CLAUDE_SYSTEM,
        ]
        if self.effort:
            argv += ["--effort", self.effort]
        if self.tools:
            argv += ["--allowedTools", self.tools]
        # Empty working dir: the agent must not see project files.
        with tempfile.TemporaryDirectory(prefix="subtitlekit-llm-") as cwd:
            try:
                proc = self.runner(argv, cwd, self.timeout, prompt)
            except subprocess.TimeoutExpired as exc:
                raise LLMError(f"claude timed out after {self.timeout:.0f} s") from exc
            except OSError as exc:
                raise LLMError(f"claude failed to run: {exc}") from exc
        if proc.returncode != 0:
            raise LLMError(f"claude exit {proc.returncode}: {(proc.stderr or proc.stdout)[-300:]}")
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise LLMError(f"claude returned invalid JSON: {proc.stdout[:200]!r}") from exc
        if not isinstance(data, dict):
            raise LLMError(f"claude returned unexpected JSON: {proc.stdout[:200]!r}")
        if data.get("is_error"):
            raise LLMError(f"claude error: {str(data.get('result'))[:300]}")
        result = data.get("result")
        if not isinstance(result, str) or not result.strip():
            raise LLMError("claude returned no text")
        return result


# agy runs an agent: asked for exact character counts, Gemini Flash tries to run a command, the call is
# denied and the turn ends with "The stream was interrupted" (E7). This line keeps it to a text answer.
AGY_TEXT_ONLY = "Do not use any tools or run any commands: answer directly in text.\n\n"


@dataclass
class AgyBackend(LLMBackend):
    """Antigravity CLI headless (`agy --print`); the prompt is attached to --print= so a leading dash is safe."""

    model: str = "gemini-3.8-flash-high"
    binary: str = "agy"
    timeout: float = 300.0
    runner: Runner = field(default=_run, repr=False)
    name: str = "agy"

    def complete(self, prompt: str) -> str:
        argv = [
            self.binary, f"--print={AGY_TEXT_ONLY}{prompt}", "--model", self.model, "--output-format", "json",
            "--disable-slash-commands", "--print-timeout", f"{int(self.timeout)}s",
        ]
        # Empty working dir: the agent must not see project files.
        with tempfile.TemporaryDirectory(prefix="subtitlekit-llm-") as cwd:
            try:
                proc = self.runner(argv, cwd, self.timeout)
            except subprocess.TimeoutExpired as exc:
                raise LLMError(f"agy timed out after {self.timeout:.0f} s") from exc
            except OSError as exc:
                raise LLMError(f"agy failed to run: {exc}") from exc
        if proc.returncode != 0:
            raise LLMError(f"agy exit {proc.returncode}: {(proc.stderr or proc.stdout)[-300:]}")
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise LLMError(f"agy returned invalid JSON: {proc.stdout[:200]!r}") from exc
        if not isinstance(data, dict):
            raise LLMError(f"agy returned unexpected JSON: {proc.stdout[:200]!r}")
        if data.get("status") != "SUCCESS":
            raise LLMError(f"agy status {data.get('status')!r}: {str(data.get('response'))[:300]}")
        response = data.get("response")
        if not isinstance(response, str) or not response.strip():
            raise LLMError("agy returned no text")
        return response


BRIDGE_TEXT_ONLY = ("Answer from the text below only: do not run commands, read or write files, or browse. "
                    "Reply with the requested output only.\n\n")


@dataclass
class BridgeBackend(LLMBackend):
    """Codex via agent-bridge: enqueue an `exec` job, then wait for it (no deadline argument).

    For model comparisons only. The bridge worker runs Codex in its own sandbox and accepts no isolation
    flags from the client, so the prompt itself asks for a text-only answer (BRIDGE_TEXT_ONLY).
    """

    model: str = "gpt-5.6-luna"
    effort: str = "medium"
    client: str = field(default_factory=lambda: os.path.expanduser("~/agent-bridge/agent_client.py"))
    timeout: float = 1800.0
    runner: Runner = field(default=_run, repr=False)
    name: str = "bridge"

    def _call(self, argv: List[str], cwd: str, what: str) -> Dict[str, Any]:
        try:
            proc = self.runner(argv, cwd, self.timeout)
        except subprocess.TimeoutExpired as exc:
            raise LLMError(f"bridge {what} timed out after {self.timeout:.0f} s") from exc
        except OSError as exc:
            raise LLMError(f"bridge {what} failed to run: {exc}") from exc
        if proc.returncode != 0:
            raise LLMError(f"bridge {what} exit {proc.returncode}: {(proc.stderr or proc.stdout)[-300:]}")
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise LLMError(f"bridge {what} returned invalid JSON: {proc.stdout[:200]!r}") from exc
        if not isinstance(data, dict):
            raise LLMError(f"bridge {what} returned unexpected JSON: {proc.stdout[:200]!r}")
        return data

    def complete(self, prompt: str) -> str:
        enqueue = [
            "python3", self.client, "enqueue", "exec", "-c", f"model={self.model}",
            "-c", f"model_reasoning_effort={self.effort}", BRIDGE_TEXT_ONLY + prompt,
        ]
        with tempfile.TemporaryDirectory(prefix="subtitlekit-llm-") as cwd:
            job_id = self._call(enqueue, cwd, "enqueue").get("job_id")
            if not isinstance(job_id, str) or not job_id:
                raise LLMError("bridge enqueue returned no job_id")
            done = self._call(["python3", self.client, "wait", job_id], cwd, "wait")
        if done.get("status") != "completed":
            raise LLMError(f"bridge job {job_id} ended with status {done.get('status')!r}")
        text = done.get("output")
        if text is None and done.get("output_file"):
            try:
                with open(done["output_file"], encoding="utf-8") as fh:
                    text = fh.read()
            except OSError as exc:
                raise LLMError(f"bridge output file unreadable: {exc}") from exc
        if not isinstance(text, str) or not text.strip():
            raise LLMError("bridge returned no text")
        return text


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

        # Settings that change the reply are part of the key; none set keeps the old keys valid.
        extras = "".join(f"{k}={getattr(self.inner, k)}|" for k in ("effort", "tools") if getattr(self.inner, k, ""))
        key = f"{self.inner.name}|{getattr(self.inner, 'model', '')}|{extras}{prompt}"
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
    opencode = OpenCodeBackend(model=cfg.get("opencode_model", cfg.get("model", "opencode/big-pickle")), timeout=timeout)
    gemini = GeminiCliBackend(model=cfg.get("gemini_model"), timeout=timeout)
    if kind == "opencode":
        return opencode
    if kind == "gemini":
        return gemini
    if kind == "claude":
        return ClaudeCliBackend(model=cfg.get("claude_model", "claude-haiku-5-5"), effort=cfg.get("claude_effort", ""),
                                timeout=timeout,
                                tools=cfg.get("claude_tools", ""))
    if kind == "agy":
        return AgyBackend(model=cfg.get("agy_model", "gemini-3.8-flash-high"), timeout=timeout)
    if kind == "bridge":
        return BridgeBackend(model=cfg.get("bridge_model", "gpt-5.6-luna"),
                             effort=cfg.get("bridge_effort", "medium"), timeout=timeout)
    if kind == "fallback":
        return FallbackBackend([opencode, gemini])
    if kind == "mock":
        return MockBackend(replies=lambda prompt: "{}")
    raise ValueError(f"unknown llm backend: {kind}")
