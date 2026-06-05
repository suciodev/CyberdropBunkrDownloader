"""
Shared bookmarks I/O: load, save, and normalise bookmarks.yml data.
All modules that read or write bookmarks should import from here.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml


def load_bookmarks(filepath: str) -> dict:
    """Load bookmarks from YAML file. Returns empty structure if file doesn't exist."""
    path = Path(filepath)
    if not path.exists():
        return {"creators": []}
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
        return data if data else {"creators": []}


def save_bookmarks(filepath: str, data: dict) -> None:
    """Save bookmarks to YAML file."""
    with open(filepath, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


def normalize_bookmarks(bookmarks: dict) -> dict:
    """
    Normalise all link entries to dicts with 'name', 'url', and 'downloaded' keys.
    Accepts both string-only links (just a URL) and full dict links.
    Mutates and returns the bookmarks dict.
    """
    for creator in bookmarks.get("creators", []):
        links = creator.get("links", [])
        normalised = []
        for i, link in enumerate(links):
            if isinstance(link, str):
                normalised.append({"name": f"Link {i + 1}", "url": link, "downloaded": False})
            else:
                normalised.append(
                    {
                        "name": link.get("name", f"Link {i + 1}"),
                        "url": link.get("url"),
                        "downloaded": link.get("downloaded", False),
                    }
                )
        creator["links"] = normalised
    return bookmarks


def sanitize_filename(name: str) -> str:
    """Remove characters illegal in filenames. Used for album/file naming."""
    if name is None:
        return ""
    return re.sub(r'[<>:"/\\|?*\']|[\0-\x1f]', "-", name).strip()
