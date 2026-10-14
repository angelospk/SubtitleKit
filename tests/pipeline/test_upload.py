import subprocess

from subtitlekit.pipeline.upload import plan_upload

FILM = {"imdb_id": "tt1371111", "release": "Film.2025.1080p.WEB-DL", "fps": 23.976}
CFG = {"cli_path": "/opt/upload_cli", "translator": "haroldpoi", "comment": "LLM translation, human checked"}
ENV = {"OS_USERNAME": "harold", "OS_PASSWORD": "s3cret"}


class Spy:
    def __init__(self):
        self.calls = []

    def __call__(self, argv):
        self.calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="uploaded s3cret ok", stderr="")


def test_dry_run_is_default_and_builds_exact_command():
    spy = Spy()
    plan = plan_upload("/out/film.el.srt", FILM, CFG, env=ENV, runner=spy)
    assert plan.dry_run and not plan.executed and spy.calls == []
    assert plan.argv == [
        "/opt/upload_cli", "-username=$OS_USERNAME", "-password=***", "-subtitle=/out/film.el.srt",
        "-imdb=1371111", "-lang=ell", "-release=Film.2025.1080p.WEB-DL", "-translator=haroldpoi",
        "-comment=LLM translation, human checked", "-fps=23.976", "-auto",
    ]
    assert "s3cret" not in plan.command


def test_really_upload_refused_unless_config_allows():
    spy = Spy()
    plan = plan_upload("/out/f.srt", FILM, CFG, really_upload=True, env=ENV, runner=spy)
    assert spy.calls == [] and plan.dry_run
    assert "allow_real_upload" in plan.problems[0]


def test_really_upload_refused_without_credentials():
    spy = Spy()
    plan = plan_upload("/out/f.srt", FILM, {**CFG, "allow_real_upload": True}, really_upload=True, env={}, runner=spy)
    assert spy.calls == [] and "credentials" in plan.problems[0]


def test_real_upload_path_redacts_password_everywhere():
    spy = Spy()
    plan = plan_upload("/out/f.srt", FILM, {**CFG, "allow_real_upload": True}, really_upload=True, env=ENV, runner=spy)
    assert plan.executed and not plan.dry_run
    assert "-password=s3cret" in spy.calls[0]  # the real process gets the secret
    assert "s3cret" not in plan.command and "s3cret" not in plan.output
    assert "s3cret" not in str(plan.to_dict())


def test_missing_imdb_is_reported_and_blocks_real_upload():
    spy = Spy()
    plan = plan_upload("/out/f.srt", {}, {**CFG, "allow_real_upload": True}, really_upload=True, env=ENV, runner=spy)
    assert spy.calls == []
    assert any("imdb" in p for p in plan.problems)


def test_auto_flag_can_be_disabled_for_human_translations():
    plan = plan_upload("/out/f.srt", FILM, {**CFG, "automatic_translation": False})
    assert "-auto" not in plan.argv
