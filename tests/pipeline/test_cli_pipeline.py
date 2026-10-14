import json
import sys

from subtitlekit.cli.main import main
from subtitlekit.pipeline.srt import Cue, format_srt

FRAME = 1000 / 23.976


def film(tmp_path):
    d = tmp_path / "Film.2025"
    d.mkdir()
    cues = [Cue(i + 1, int((24 + 72 * i) * FRAME), int((84 + 72 * i) * FRAME), f"Hello number {i}, friend.")
            for i in range(40)]
    (d / "Film.2025.WEB-DL.eng.srt").write_text(format_srt(cues), encoding="utf-8")
    (d / "film.yaml").write_text("title: Film\nyear: 2025\nimdb_id: tt42\n", encoding="utf-8")
    return d


def run_cli(monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["subtitlekit", *argv])
    return main()


def test_cli_run_with_mock_llm_then_upload_dry_run(tmp_path, monkeypatch, capsys):
    d = film(tmp_path)
    out = tmp_path / "out"
    assert run_cli(monkeypatch, "pipeline", "run", str(d), "--mock-llm", "--out", str(out)) == 0
    text = capsys.readouterr().out
    assert "mock-transliterate" in text and "==> Film.2025:" in text
    report = json.loads((out / "Film.2025" / "report.json").read_text(encoding="utf-8"))
    assert report["translation"]["backend"] == "mock-transliterate"
    assert run_cli(monkeypatch, "pipeline", "upload", str(out / "Film.2025")) == 0
    assert "DRY-RUN, not executed:" in capsys.readouterr().out


def test_cli_upload_really_refused_by_default_config(tmp_path, monkeypatch, capsys):
    d = film(tmp_path)
    out = tmp_path / "out"
    run_cli(monkeypatch, "pipeline", "run", str(d), "--mock-llm", "--out", str(out))
    capsys.readouterr()
    monkeypatch.setenv("OS_USERNAME", "u")
    monkeypatch.setenv("OS_PASSWORD", "p")
    assert run_cli(monkeypatch, "pipeline", "upload", str(out / "Film.2025"), "--really-upload") == 0
    printed = capsys.readouterr().out
    assert "DRY-RUN" in printed and "allow_real_upload" in printed


def test_cli_analyze_and_init_config(tmp_path, monkeypatch, capsys):
    d = film(tmp_path)
    assert run_cli(monkeypatch, "pipeline", "analyze", str(d)) == 0
    assert "chosen source:" in capsys.readouterr().out
    cfg = tmp_path / "pipeline.yaml"
    assert run_cli(monkeypatch, "pipeline", "init-config", "-o", str(cfg)) == 0
    assert "allow_real_upload: false" in cfg.read_text(encoding="utf-8")
    assert run_cli(monkeypatch, "pipeline", "queue", "--out", str(tmp_path / "none")) == 0
    assert "empty" in capsys.readouterr().out


def test_cli_run_continues_after_a_broken_film(tmp_path, monkeypatch, capsys):
    good = film(tmp_path)
    bad = tmp_path / "Broken.2025"
    bad.mkdir()
    (bad / "film.yaml").write_text("title: a: b\n", encoding="utf-8")
    out = tmp_path / "out"
    code = run_cli(monkeypatch, "pipeline", "run", str(bad), str(good), "--mock-llm", "--out", str(out))
    printed = capsys.readouterr()
    assert code == 1
    assert "Broken.2025: ERROR" in printed.out and "==> Film.2025:" in printed.out
    assert (out / "Film.2025" / "report.json").exists()
