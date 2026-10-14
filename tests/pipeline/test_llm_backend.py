import subprocess

import pytest

from subtitlekit.pipeline.llm import (
    CachingBackend,
    FallbackBackend,
    GeminiCliBackend,
    LLMError,
    MockBackend,
    OpenCodeBackend,
    extract_json,
    make_backend,
    parse_opencode_json,
)

OPENCODE_STDOUT = "\n".join(
    [
        '{"type":"step_start","part":{"type":"step-start"}}',
        '{"type":"text","part":{"type":"text","text":"{\\"1\\": \\"Γεια\\"}"}}',
        '{"type":"step_finish","part":{"type":"step-finish"}}',
    ]
)


def fake_runner(stdout="", returncode=0, calls=None):
    def run(argv, cwd, timeout):
        if calls is not None:
            calls.append((argv, cwd))
        return subprocess.CompletedProcess(argv, returncode, stdout=stdout, stderr="boom")

    return run


def test_parse_opencode_json_joins_text_parts():
    assert parse_opencode_json(OPENCODE_STDOUT) == '{"1": "Γεια"}'


def test_opencode_backend_builds_argv_and_runs_in_temp_dir():
    calls = []
    backend = OpenCodeBackend(model="opencode/x-free", runner=fake_runner(OPENCODE_STDOUT, calls=calls))
    assert backend.complete("hi") == '{"1": "Γεια"}'
    argv, cwd = calls[0]
    assert argv == ["opencode", "run", "--format", "json", "-m", "opencode/x-free", "hi"]
    assert "subtitlekit-llm-" in cwd


def test_opencode_backend_raises_on_failure():
    with pytest.raises(LLMError):
        OpenCodeBackend(runner=fake_runner("", returncode=1)).complete("hi")
    with pytest.raises(LLMError):
        OpenCodeBackend(runner=fake_runner('{"type":"step_start","part":{}}')).complete("hi")


def test_gemini_backend_uses_skip_trust():
    calls = []
    out = GeminiCliBackend(runner=fake_runner("OK", calls=calls)).complete("p")
    assert out == "OK"
    assert calls[0][0][:2] == ["gemini", "--skip-trust"]


def test_fallback_uses_next_backend_on_error():
    bad = OpenCodeBackend(runner=fake_runner("", returncode=2))
    good = MockBackend(replies=["fine"])
    assert FallbackBackend([bad, good]).complete("x") == "fine"
    with pytest.raises(LLMError):
        FallbackBackend([bad]).complete("x")


def test_mock_backend_records_prompts_and_runs_out():
    mock = MockBackend(replies=["a"])
    assert mock.complete("p1") == "a"
    assert mock.prompts == ["p1"]
    with pytest.raises(LLMError):
        mock.complete("p2")


@pytest.mark.parametrize(
    "reply",
    ['{"a": 1}', 'Sure!\n```json\n{"a": 1}\n```', 'noise {"a": 1} trailing'],
)
def test_extract_json_tolerates_noise(reply):
    assert extract_json(reply) == {"a": 1}


def test_extract_json_raises_without_json():
    with pytest.raises(LLMError):
        extract_json("no json here")


def test_make_backend_kinds():
    assert make_backend({"backend": "opencode"}).name == "opencode"
    assert make_backend({"backend": "fallback"}).name == "fallback"
    with pytest.raises(ValueError):
        make_backend({"backend": "nope"})


def test_caching_backend_reuses_successful_replies_only(tmp_path):
    inner = MockBackend(replies=["one", "two"])
    cached = CachingBackend(inner=inner, cache_dir=str(tmp_path))
    assert cached.complete("p") == "one"
    assert cached.complete("p") == "one" and cached.hits == 1
    assert cached.complete("q") == "two"
    assert cached.name == "mock"
    failing = CachingBackend(inner=MockBackend(replies=[]), cache_dir=str(tmp_path / "f"))
    with pytest.raises(LLMError):
        failing.complete("x")
    assert not (tmp_path / "f").exists() or not any((tmp_path / "f").rglob("*.txt"))


def test_make_backend_wraps_cache_when_configured(tmp_path):
    b = make_backend({"backend": "opencode", "cache_dir": str(tmp_path)})
    assert isinstance(b, CachingBackend) and b.name == "opencode"


def test_forget_evicts_rejected_reply_and_cache_errors_are_tolerated(tmp_path):
    from subtitlekit.pipeline.llm import forget

    inner = MockBackend(replies=["bad", "good"])
    cached = CachingBackend(inner=inner, cache_dir=str(tmp_path))
    assert cached.complete("p") == "bad"
    forget(cached, "p")
    assert cached.complete("p") == "good"
    forget(MockBackend(), "p")  # no-op on non-caching backends
    blocked = tmp_path / "file"
    blocked.write_text("x")
    unwritable = CachingBackend(inner=MockBackend(replies=["ok"]), cache_dir=str(blocked))
    assert unwritable.complete("p") == "ok"


def test_claude_cli_backend_sends_prompt_on_stdin_and_parses_result():
    from subtitlekit.pipeline.llm import ClaudeCliBackend

    calls = []

    def run(argv, cwd, timeout, input_text):
        calls.append((argv, cwd, input_text))
        return subprocess.CompletedProcess(argv, 0, stdout='{"type":"result","is_error":false,"result":"{\\"1\\": \\"Γεια\\"}"}', stderr="")

    backend = ClaudeCliBackend(runner=run)
    assert backend.complete("hi there") == '{"1": "Γεια"}'
    argv, cwd, input_text = calls[0]
    assert argv[:4] == ["claude", "-p", "--model", "claude-haiku-5-5"]
    for flag in ("--output-format", "--setting-sources", "--tools", "--no-session-persistence", "--system-prompt",
                 "--strict-mcp-config"):
        assert flag in argv
    assert argv[argv.index("--output-format") + 1] == "json"
    assert argv[argv.index("--setting-sources") + 1] == ""
    assert argv[argv.index("--tools") + 1] == ""
    assert "hi there" not in argv  # the prompt never appears in the process list
    assert input_text == "hi there"
    assert "subtitlekit-llm-" in cwd
    assert backend.name == "claude"


def test_claude_cli_backend_raises_on_errors():
    from subtitlekit.pipeline.llm import ClaudeCliBackend

    def runner(stdout, code=0):
        return lambda argv, cwd, timeout, input_text: subprocess.CompletedProcess(argv, code, stdout=stdout, stderr="x")

    for stdout, code in [
        ('{"type":"result","is_error":true,"result":"rate limited"}', 0),
        ("not json", 0),
        ('{"type":"result","is_error":false,"result":"  "}', 0),
        ('{"type":"result","is_error":false,"result":"ok"}', 1),
    ]:
        with pytest.raises(LLMError):
            ClaudeCliBackend(runner=runner(stdout, code)).complete("p")


def test_make_backend_builds_claude_backend():
    from subtitlekit.pipeline.llm import ClaudeCliBackend

    backend = make_backend({"backend": "claude", "claude_model": "claude-sonnet-5-5", "timeout_s": 60})
    assert isinstance(backend, ClaudeCliBackend)
    assert backend.model == "claude-sonnet-5-5" and backend.timeout == 60
    assert make_backend({"backend": "claude"}).model == "claude-haiku-5-5"


def test_opencode_error_event_is_reported_even_with_nonzero_exit():
    stdout = '{"type":"error","error":{"message":"getaddrinfo ENOTFOUND opencode.ai"}}'
    with pytest.raises(LLMError, match="ENOTFOUND"):
        OpenCodeBackend(runner=fake_runner(stdout, returncode=1)).complete("hi")
