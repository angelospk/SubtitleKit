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
