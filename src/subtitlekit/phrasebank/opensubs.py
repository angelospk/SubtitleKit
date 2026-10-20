"""OpenSubtitles REST API client, gated on an API key."""

from __future__ import annotations

import os
import re
from typing import Dict, List, Optional, Tuple

import requests

from ..pipeline.analyzer import PRO_RANKS, RELEASE_CAM_RE, RELEASE_PRO_RE

API = "https://api.opensubtitles.com/api/v1"
USER_AGENT = "subtitlekit-phrasebank v0.1"


TIMEOUT = 60


class MissingKey(RuntimeError):
    """No OpenSubtitles API key configured."""


def load_key(path: Optional[str]) -> Optional[str]:
    """Key from ``OPENSUBTITLES_API_KEY``, else from ``path``, else None."""
    key = os.environ.get("OPENSUBTITLES_API_KEY")
    if key:
        return key.strip() or None
    if not path:
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read().strip() or None
    except OSError:
        return None


def is_professional(attrs: Dict) -> Tuple[bool, List[str]]:
    """Retail/trusted evidence, with cam and machine-translation vetoes first."""
    reasons: List[str] = []
    release = str(attrs.get("release") or "")
    if attrs.get("ai_translated"):
        return False, ["AI translated"]
    if attrs.get("machine_translated"):
        return False, ["machine translated"]
    if RELEASE_CAM_RE.search(release):
        return False, [f"cam release: {release}"]
    if attrs.get("from_trusted"):
        reasons.append("trusted uploader")
    if RELEASE_PRO_RE.search(release):
        reasons.append(f"retail release: {release}")
    rank = str((attrs.get("uploader") or {}).get("rank") or "").lower()
    if rank in PRO_RANKS:
        reasons.append(f"uploader rank: {rank}")
    return bool(reasons), reasons


class OpenSubtitlesClient:
    """Minimal client: search, filter professionals, login, download."""

    def __init__(
        self,
        api_key: Optional[str],
        username: Optional[str] = None,
        password: Optional[str] = None,
        user_agent: str = USER_AGENT,
        session: Optional[requests.Session] = None,
    ) -> None:
        if not api_key:
            raise MissingKey("OPENSUBTITLES_API_KEY is not set")
        self.api_key = api_key
        self.username = username
        self.password = password
        self.user_agent = user_agent
        self.session = session or requests.Session()
        self.token: Optional[str] = None

    def _headers(self, auth: bool = False) -> Dict[str, str]:
        headers = {
            "Api-Key": self.api_key,
            "User-Agent": self.user_agent,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if auth and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def search(self, imdb_id: str, language: str = "el") -> List[Dict]:
        """Raw subtitle items for one IMDb id."""
        digits = re.sub(r"\D", "", imdb_id).lstrip("0")
        resp = self.session.request(
            "GET",
            f"{API}/subtitles",
            headers=self._headers(),
            params={"imdb_id": digits, "languages": language},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json().get("data", [])

    def search_professional(self, imdb_id: str, language: str = "el") -> List[Dict]:
        """First file of every professional item."""
        out: List[Dict] = []
        for item in self.search(imdb_id, language):
            attrs = item.get("attributes") or {}
            ok, reasons = is_professional(attrs)
            files = attrs.get("files") or []
            if not ok or not files:
                continue
            out.append(
                {
                    "file_id": files[0].get("file_id"),
                    "file_name": files[0].get("file_name"),
                    "release": attrs.get("release"),
                    "subtitle_id": item.get("id"),
                    "download_count": attrs.get("download_count") or 0,
                    "reasons": reasons,
                }
            )
        return out

    def login(self) -> str:
        resp = self.session.request(
            "POST",
            f"{API}/login",
            headers=self._headers(),
            json={"username": self.username, "password": self.password},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        self.token = resp.json().get("token")
        return self.token or ""

    def download(self, file_id: int) -> bytes:
        if not self.token:
            self.login()
        resp = self.session.request(
            "POST",
            f"{API}/download",
            headers=self._headers(auth=True),
            json={"file_id": file_id},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        link = resp.json()["link"]
        content = self.session.request("GET", link, timeout=TIMEOUT)
        content.raise_for_status()
        return content.content
