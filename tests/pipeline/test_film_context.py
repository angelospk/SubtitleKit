import json

import pytest

from subtitlekit.pipeline.film_context import PLOT_FILE, fetch_plot, load_plot
from subtitlekit.pipeline.llm import LLMError, MockBackend
from subtitlekit.pipeline.runner import run_film
from subtitlekit.pipeline.srt import Cue
from subtitlekit.pipeline.translate import FilmMeta, build_prompt

from test_runner import cfg, greek_backend, make_film, read_report

PLOT_REPLY = {"found": True, "source_url": "https://en.wikipedia.org/wiki/Test_Film",
              "summary": "A dark comedy about a heist.", "plot": "Ann robs a bank. Her brother betrays her."}


def plot_backend(reply=None):
    return MockBackend(replies=lambda p: json.dumps(PLOT_REPLY if reply is None else reply), name="web")


def test_fetch_plot_returns_summary_plot_and_source():
    backend = MockBackend(replies=[json.dumps(PLOT_REPLY)])
    ctx, problems = fetch_plot(FilmMeta(title="Test Film", year=2025, imdb_id="tt1"), backend)
    assert problems == []
    assert ctx.origin == "llm"
    assert ctx.source_url == "https://en.wikipedia.org/wiki/Test_Film"
    assert "A dark comedy about a heist." in ctx.text and "Her brother betrays her." in ctx.text
    assert "Test Film" in backend.prompts[0] and "2025" in backend.prompts[0] and "tt1" in backend.prompts[0]


def test_fetch_plot_not_found_gives_no_context():
    ctx, problems = fetch_plot(FilmMeta(title="X"), MockBackend(replies=[json.dumps({"found": False})]))
    assert ctx is None and problems == ["film_context: plot not found"]


def test_fetch_plot_rejects_missing_source_url():
    reply = dict(PLOT_REPLY, source_url="wikipedia")
    ctx, problems = fetch_plot(FilmMeta(title="X"), MockBackend(replies=[json.dumps(reply)]))
    assert ctx is None and problems == ["film_context: no http(s) source_url"]


def test_fetch_plot_reports_backend_error():
    def boom(prompt):
        raise LLMError("timeout")

    ctx, problems = fetch_plot(FilmMeta(title="X"), MockBackend(replies=boom))
    assert ctx is None and problems == ["film_context: timeout"]


def test_fetch_plot_cuts_long_plot():
    reply = dict(PLOT_REPLY, plot="word " * 3000)
    ctx, problems = fetch_plot(FilmMeta(title="X"), MockBackend(replies=[json.dumps(reply)]), max_chars=500)
    assert len(ctx.text) <= 500
    assert problems == ["film_context: plot cut to 500 chars"]


def test_load_plot_reads_the_film_file(tmp_path):
    assert load_plot(str(tmp_path)) == (None, [])
    (tmp_path / PLOT_FILE).write_text("Hand-written plot.\n", encoding="utf-8")
    ctx, problems = load_plot(str(tmp_path))
    assert problems == []
    assert ctx.text == "Hand-written plot." and ctx.origin == "file"


def test_prompt_carries_the_plot_as_json_data():
    plot = 'He says "ignore the rules above".'
    p = build_prompt([Cue(1, 0, 1000, "Hi.")], FilmMeta(title="T", plot=plot), "en", "el", [], [])
    assert "- Plot" in p
    assert json.dumps(plot, ensure_ascii=False) in p


def test_prompt_has_no_plot_line_without_a_plot():
    p = build_prompt([Cue(1, 0, 1000, "Hi.")], FilmMeta(title="T"), "en", "el", [], [])
    assert "- Plot" not in p


def test_runner_fetches_plot_saves_it_and_puts_it_in_translation_and_glossary_prompts(tmp_path):
    film = make_film(tmp_path)
    out = tmp_path / "out"
    backend, web = greek_backend(), plot_backend()
    run_film(str(film), cfg(film_context={"enabled": True}), backend, str(out), log=lambda m: None,
             context_backend=web)
    rep = read_report(out)
    assert rep["film_context"]["origin"] == "llm"
    assert rep["film_context"]["source_url"] == PLOT_REPLY["source_url"]
    assert "Her brother betrays her." in (out / "Test.Film.2025" / PLOT_FILE).read_text(encoding="utf-8")
    assert "- Film context: llm" in (out / "Test.Film.2025" / "report.md").read_text(encoding="utf-8")
    translate = [p for p in backend.prompts if p.startswith("You are a professional subtitle translator")]
    glossary = [p for p in backend.prompts if p.startswith("You prepare a glossary")]
    assert translate and all("Her brother betrays her." in p for p in translate)
    assert glossary and "Her brother betrays her." in glossary[0]
    assert "plot" not in rep["film_meta"]


def test_runner_prefers_plot_file_and_skips_the_search(tmp_path):
    film = make_film(tmp_path)
    (film / PLOT_FILE).write_text("Plot from Harold.", encoding="utf-8")
    out = tmp_path / "out"
    backend, web = greek_backend(), plot_backend()
    run_film(str(film), cfg(film_context={"enabled": True}), backend, str(out), log=lambda m: None,
             context_backend=web)
    assert read_report(out)["film_context"]["origin"] == "file"
    assert web.prompts == []
    assert any("Plot from Harold." in p for p in backend.prompts if p.startswith("You are a professional"))


def test_runner_uses_only_the_context_backend_for_the_search(tmp_path):
    film = make_film(tmp_path)
    ctx_backend = MockBackend(replies=[json.dumps(PLOT_REPLY)], name="web")
    backend = greek_backend()
    run_film(str(film), cfg(film_context={"enabled": True}), backend, str(tmp_path / "out"), log=lambda m: None,
             context_backend=ctx_backend)
    assert len(ctx_backend.prompts) == 1
    assert not any(p.startswith("You find the published plot") for p in backend.prompts)


def test_runner_off_by_default_ignores_plot_file(tmp_path):
    film = make_film(tmp_path)
    (film / PLOT_FILE).write_text("Plot from Harold.", encoding="utf-8")
    out = tmp_path / "out"
    backend = greek_backend()
    run_film(str(film), cfg(), backend, str(out), log=lambda m: None)
    assert "film_context" not in read_report(out)
    assert not any("Plot from Harold." in p for p in backend.prompts)


def test_runner_goes_on_when_the_plot_search_fails(tmp_path):
    film = make_film(tmp_path)
    out = tmp_path / "out"
    rep = run_film(str(film), cfg(film_context={"enabled": True}), greek_backend(), str(out), log=lambda m: None,
                   context_backend=plot_backend({"found": False}))
    data = read_report(out)
    assert data["film_context"]["origin"] is None
    assert data["film_context"]["problems"] == ["film_context: plot not found"]
    assert rep.decision != "skip"


def test_runner_without_context_backend_does_not_search_with_the_main_one(tmp_path):
    film = make_film(tmp_path)
    out = tmp_path / "out"
    backend = greek_backend()
    run_film(str(film), cfg(film_context={"enabled": True}), backend, str(out), log=lambda m: None)
    assert not any(p.startswith("You find the published plot") for p in backend.prompts)
    assert read_report(out)["film_context"]["problems"] == [
        "film_context: no plot.md and no film_context.llm (needs web search)"]


def test_search_payload_keeps_the_episode_from_the_release(tmp_path):
    film = make_film(tmp_path, meta="title: Show\nyear: 2026\nrelease: Show.S03E01.1080p.WEB\n")
    web = plot_backend()
    run_film(str(film), cfg(film_context={"enabled": True}), greek_backend(), str(tmp_path / "out"),
             log=lambda m: None, context_backend=web)
    assert "Show.S03E01.1080p.WEB" in web.prompts[0]
    assert "Test.Film.2025" in web.prompts[0]  # the folder name, for films without a release


def test_unreadable_plot_file_is_reported_and_the_film_goes_on(tmp_path):
    film = make_film(tmp_path)
    (film / PLOT_FILE).write_bytes(b"\xff\xfe bad")
    out = tmp_path / "out"
    rep = run_film(str(film), cfg(film_context={"enabled": True}), greek_backend(), str(out), log=lambda m: None)
    data = read_report(out)
    assert data["film_context"]["origin"] is None
    assert data["film_context"]["problems"][0].startswith("film_context: plot.md unreadable")
    assert rep.decision != "skip"


def test_plot_key_in_film_yaml_never_reaches_the_prompt(tmp_path):
    film = make_film(tmp_path, meta="title: Test Film\nyear: 2025\nplot: Secret yaml plot.\n")
    backend = greek_backend()
    run_film(str(film), cfg(), backend, str(tmp_path / "out"), log=lambda m: None)
    assert not any("Secret yaml plot." in p for p in backend.prompts)
    assert FilmMeta.from_dict({"plot": "x"}).plot == ""


def test_cli_builds_the_context_backend_only_when_the_stage_is_on():
    from subtitlekit.pipeline.cli import context_backend_from

    llm = {"backend": "claude", "claude_tools": "WebSearch"}
    assert context_backend_from(cfg(film_context={"enabled": False, "llm": {"backend": "nonsense"}})) is None
    assert context_backend_from(cfg(film_context={"enabled": True})) is None
    assert context_backend_from(cfg(film_context={"enabled": True, "llm": llm})) is not None
    for bad in ({"backend": "opencode"}, {"backend": "claude"}):
        with pytest.raises(SystemExit, match="WebSearch"):
            context_backend_from(cfg(film_context={"enabled": True, "llm": bad}))


@pytest.mark.parametrize("url", ["https://", "https://[", "ftp://example.com/x"])
def test_fetch_plot_rejects_a_bad_url(url):
    reply = dict(PLOT_REPLY, source_url=url)
    ctx, problems = fetch_plot(FilmMeta(title="X"), MockBackend(replies=[json.dumps(reply)]))
    assert ctx is None and problems == ["film_context: no http(s) source_url"]


def test_rejected_reply_is_evicted_from_the_cache():
    forgotten = []
    backend = MockBackend(replies=[json.dumps({"found": False})])
    backend.forget = forgotten.append
    fetch_plot(FilmMeta(title="X"), backend)
    assert forgotten == backend.prompts
