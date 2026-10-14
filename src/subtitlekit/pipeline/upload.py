"""Upload stage: build the exact ``upload_cli`` command (opensubtitles-go).

DRY-RUN by default. The real upload runs only when BOTH the config says
``upload.allow_real_upload: true`` AND the caller passes ``really_upload=True``
(CLI ``--really-upload``) AND credentials are present in the environment.
The password never appears in logs or reports (it is replaced by ``***``).

Upload CLI: ~/projects/osgolang/opensubtitles-go/examples/upload_cli
(legacy XML-RPC upload; flags documented in its main.go).
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional

ISO639_2 = {"el": "ell", "en": "eng", "fr": "fre", "de": "ger", "es": "spa", "it": "ita"}
REDACTED = "***"


@dataclass
class UploadPlan:
    argv: List[str]  # redacted, safe to log
    dry_run: bool
    executed: bool = False
    returncode: Optional[int] = None
    output: str = ""
    problems: List[str] = field(default_factory=list)

    @property
    def command(self) -> str:
        import shlex

        return " ".join(shlex.quote(a) for a in self.argv)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["command"] = self.command
        return d


def build_upload_argv(
    subtitle_path: str, film: Dict[str, Any], upload_cfg: Dict[str, Any],
    language: str = "el", password: str = REDACTED, username: str = "",
) -> (List[str], List[str]):
    """Return (argv, problems). ``problems`` lists missing required inputs."""
    problems = []
    imdb = re.sub(r"\D", "", str(film.get("imdb_id", "")))
    if not imdb:
        problems.append("film imdb_id missing (required by upload_cli -imdb)")
    cli = os.path.expanduser(upload_cfg.get("cli_path", "upload_cli"))
    argv = [
        cli,
        f"-username={username or '$' + upload_cfg.get('username_env', 'OS_USERNAME')}",
        f"-password={password}",
        f"-subtitle={subtitle_path}",
        f"-imdb={imdb}",
        f"-lang={ISO639_2.get(language, language)}",
    ]
    if film.get("release"):
        argv.append(f"-release={film['release']}")
    if upload_cfg.get("translator"):
        argv.append(f"-translator={upload_cfg['translator']}")
    if upload_cfg.get("comment"):
        argv.append(f"-comment={upload_cfg['comment']}")
    if film.get("fps"):
        argv.append(f"-fps={film['fps']}")
    if upload_cfg.get("automatic_translation", True):
        argv.append("-auto")
    if film.get("hearing_impaired"):
        argv.append("-hi")
    return argv, problems


def plan_upload(
    subtitle_path: str, film: Dict[str, Any], upload_cfg: Dict[str, Any], language: str = "el",
    really_upload: bool = False, env: Optional[Dict[str, str]] = None,
    runner: Callable[[List[str]], "subprocess.CompletedProcess[str]"] = None,
) -> UploadPlan:
    env = dict(os.environ if env is None else env)
    argv, problems = build_upload_argv(subtitle_path, film, upload_cfg, language)
    allowed = bool(upload_cfg.get("allow_real_upload", False))
    plan = UploadPlan(argv=argv, dry_run=True, problems=problems)
    if not really_upload:
        return plan
    if not allowed:
        plan.problems.append("real upload refused: upload.allow_real_upload is false in the config")
        return plan
    user = env.get(upload_cfg.get("username_env", "OS_USERNAME"), "")
    pwd = env.get(upload_cfg.get("password_env", "OS_PASSWORD"), "")
    if not user or not pwd:
        plan.problems.append("real upload refused: credentials not set in the environment")
        return plan
    if problems:
        return plan
    real_argv, _ = build_upload_argv(subtitle_path, film, upload_cfg, language, password=pwd, username=user)
    run = runner or (lambda a: subprocess.run(a, capture_output=True, text=True, timeout=300))
    plan.dry_run = False
    plan.executed = True
    try:
        proc = run(real_argv)
    except Exception as exc:  # TimeoutExpired etc. carry the argv: never let it escape
        plan.returncode = -1
        plan.output = f"{type(exc).__name__}: " + str(exc).replace(pwd, REDACTED)[-500:]
        return plan
    plan.returncode = proc.returncode
    plan.output = (proc.stdout + proc.stderr).replace(pwd, REDACTED)[-2000:]
    return plan
