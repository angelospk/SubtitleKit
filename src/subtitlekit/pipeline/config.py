"""Pipeline configuration: defaults + YAML file, deep-merged."""

from __future__ import annotations

import copy
import os
from typing import Any, Dict, Optional

DEFAULTS: Dict[str, Any] = {
    "target_language": "el",
    # Preferred source languages, best first. Also the reference languages for
    # the "1:1 uncondensed copy" machine-translation check.
    "source_languages": ["en"],
    "scan": {
        # Each subfolder of films_dir is one film: candidate .srt files plus an
        # optional film.yaml (title, year, imdb_id, release, fps, timing_reference)
        # and opensubtitles.json (API v1 search response).
        "films_dir": "~/Subtitles/films",
        "film_meta_file": "film.yaml",
    },
    "schedule": {
        # manual: run by hand. cron: the RUNBOOK shows a crontab line; the
        # pipeline itself never daemonises.
        "trigger": "manual",
        "cron": "0 3 * * *",
    },
    "worth_it": {
        "skip_if_target_professional": True,
        # Credit lines that mean "we already translated this film" (case-insensitive).
        "own_credits": ["haroldpoi"],
        "allowed_source_classes": ["professional"],
        "min_source_score": 50,
        "skip_if_only_machine_sources": True,
        "reject_release_patterns": [r"\bCAM\b", r"\bHDCAM\b", r"\bTS\b", r"TELESYNC"],
    },
    "llm": {
        "backend": "opencode",  # opencode | claude | gemini | fallback | mock
        "model": "opencode/big-pickle",
        "claude_model": "claude-haiku-5-5",
        "timeout_s": 300,
        # Successful replies are cached here (null = no cache).
        "cache_dir": "~/.cache/subtitlekit/llm",
    },
    "analysis": {
        "cps_limit": 17.0,
        "cps_hard_limit": 25.0,
        "max_line_chars": 42,
        "fps": 23.976,
        "tiny_gap_frames": 2,
        "llm_judge": False,
    },
    "translate": {"chunk_size": 40, "context_lines": 4, "max_cues": None},
    "fixes": {
        "min_gap_ms": 84,
        "min_duration_ms": 833,
        "max_duration_ms": 7000,
        "target_cps": 17.0,
        "condense_above_cps": 20.0,
        "max_line_chars": 42,
        "max_lines": 2,
        "fidelity_check": "llm",
    },
    "review": {
        # auto_approve only if every rule holds; anything else → human queue.
        "auto_approve": True,
        "max_untranslated": 0,
        "max_flag_ratio": 0.02,  # flags / cues
        "max_share_over_hard_cps": 0.01,
        "require_source_class": "professional",
        # llm: every translated cue is checked against its source; a failed or
        # missing verdict blocks auto-approve. none: always human review.
        "translation_fidelity": "llm",
    },
    "upload": {
        "enabled": True,
        # Real uploads need allow_real_upload: true here AND --really-upload
        # on the command line AND OS_USERNAME/OS_PASSWORD in the environment.
        "allow_real_upload": False,
        "cli_path": "~/projects/osgolang/opensubtitles-go/examples/upload_cli/upload_cli_mac_arm64",
        "username_env": "OS_USERNAME",
        "password_env": "OS_PASSWORD",
        # argv: password as -password= (current upload_cli) → real upload refused.
        # env: upload_cli reads OS_PASSWORD from its environment (needs a CLI change).
        "password_transport": "argv",
        "translator": "",
        "comment": "",
        "automatic_translation": True,
    },
    "output_dir": "./pipeline-out",
}


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config(path: Optional[str] = None) -> Dict[str, Any]:
    if not path:
        return copy.deepcopy(DEFAULTS)
    import yaml

    with open(os.path.expanduser(path), encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: top level must be a mapping")
    unknown = set(data) - set(DEFAULTS)
    if unknown:
        raise ValueError(f"{path}: unknown keys {sorted(unknown)}")
    return deep_merge(DEFAULTS, data)


def dump_default_config() -> str:
    import yaml

    return yaml.safe_dump(DEFAULTS, sort_keys=False, allow_unicode=True)
