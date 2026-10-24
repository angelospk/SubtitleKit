import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "table_metadata", Path(__file__).resolve().parents[2] / "docs/pipeline/eval/table/metadata.py")
metadata = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(metadata)


def test_plot_section_stops_at_the_next_top_section():
    text = "Intro.\n\n== Plot ==\nMillie is hired.\n\n=== Detail ===\nMore.\n\n== Cast ==\nSydney Sweeney"
    assert metadata.plot_section(text) == "Millie is hired.\n\n=== Detail ===\nMore."


def test_plot_section_at_the_end_of_the_extract():
    assert metadata.plot_section("Intro.\n\n== Synopsis ==\nNina hires Millie.\n") == "Nina hires Millie."


def test_plot_section_missing():
    assert metadata.plot_section("Intro only.") == ""
