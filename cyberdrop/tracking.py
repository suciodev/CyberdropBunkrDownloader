"""
Download-state tracking: DownloadTracker for per-album file dedup.
TRACKING_FILENAME is the single authoritative name for the tracking file.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path

TRACKING_FILENAME = "already_downloaded.txt"


class DownloadTracker:
    """Tracks which files have been downloaded, backed by already_downloaded.txt."""

    def __init__(self, tracking_dir: str | Path) -> None:
        self._path = Path(tracking_dir) / TRACKING_FILENAME
        self._lock = threading.Lock()

    def is_downloaded(self, key: str) -> bool:
        if not self._path.exists():
            return False
        return key in set(self._path.read_text(encoding="utf-8").splitlines())

    def mark_done(self, key: str) -> None:
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(f"{key}\n")

    def list_downloaded(self) -> list[str]:
        if not self._path.exists():
            return []
        return self._path.read_text(encoding="utf-8").splitlines()

    def ensure_exists(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._path.touch()
