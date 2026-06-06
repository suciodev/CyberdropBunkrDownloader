"""
File consolidation: move downloaded files from album staging folders into
per-creator destination directories.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Tuple

if TYPE_CHECKING:
    from .bookmarks import Bookmarks


def _normalize_name(name: str) -> str:
    """Strip to lowercase alphanumerics for fuzzy folder matching."""
    if not name:
        return ""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _folder_matches_creator(folder_name: str, creator_name: str) -> bool:
    folder_norm = _normalize_name(folder_name)
    creator_norm = _normalize_name(creator_name)
    if folder_norm == creator_norm:
        return True
    parts = [p.lower() for p in re.split(r"[^a-z]+", creator_name) if p]
    return bool(parts) and all(p in folder_norm for p in parts)


def _unique_filename(target_dir: Path, filename: str) -> str:
    if not (target_dir / filename).exists():
        return filename
    parts = filename.rsplit(".", 1)
    name, ext = (parts[0], f".{parts[1]}") if len(parts) == 2 else (filename, "")
    counter = 1
    while (target_dir / f"{name}_{counter}{ext}").exists():
        counter += 1
    return f"{name}_{counter}{ext}"


def _move_files(folder: Path, target: Path) -> Tuple[int, int, List[str], List[str]]:
    moved = dupes = 0
    skipped: List[str] = []
    errors: List[str] = []
    for item in folder.iterdir():
        if item.name.lower() == "already_downloaded.txt" or item.is_dir():
            skipped.append(item.name)
            continue
        try:
            dest_name = _unique_filename(target, item.name)
            if dest_name != item.name:
                dupes += 1
            shutil.move(str(item), str(target / dest_name))
            moved += 1
        except Exception as exc:
            errors.append(f"Failed to move {item.name}: {exc}")
    return moved, dupes, skipped, errors


def consolidate_creator_files(
    creator_name: str,
    album_names: List[str],
    source_base_dir: str,
    target_dir: str,
) -> Dict:
    """
    Move files for one creator from their album folders into target_dir.
    Handles both explicit album names and fuzzy-matched folder names.
    """
    result: Dict = {
        "success": False,
        "files_moved": 0,
        "duplicates_renamed": 0,
        "files_skipped": [],
        "errors": [],
        "message": "",
    }

    source_base = Path(source_base_dir)
    target_path = Path(target_dir)

    if not source_base.exists():
        result["errors"].append(f"Source directory not found: {source_base}")
        result["message"] = f"[-] Source directory not found: {source_base}"
        return result

    try:
        target_path.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        result["errors"].append(f"Cannot create target directory: {exc}")
        result["message"] = f"[-] Cannot create target directory: {exc}"
        return result

    moved = dupes = 0
    skipped: List[str] = []
    errors: List[str] = []
    processed: set = set()

    for album_name in album_names:
        album_dir = source_base / album_name
        if album_dir.exists() and album_dir.is_dir():
            processed.add(album_dir.name)
            m, d, s, e = _move_files(album_dir, target_path)
            moved += m; dupes += d; skipped += s; errors += e

    for item in source_base.iterdir():
        if item.is_dir() and item.name not in processed:
            if _folder_matches_creator(item.name, creator_name):
                processed.add(item.name)
                m, d, s, e = _move_files(item, target_path)
                moved += m; dupes += d; skipped += s; errors += e

    result.update({
        "success": not errors,
        "files_moved": moved,
        "duplicates_renamed": dupes,
        "files_skipped": skipped,
        "errors": errors,
        "message": (
            f"[+] {moved} files moved, {dupes} duplicates renamed"
            if not errors
            else f"[!] {moved} files moved, {len(errors)} errors"
        ),
    })
    return result


def consolidate_from_bookmarks(bookmarks: "Bookmarks", source_base_dir: str = "downloads") -> Dict:
    """
    Consolidate files for every creator that has a consolidation_path defined.
    Returns a summary dict.
    """
    consolidations: Dict = {}
    total_ok = 0

    for creator in bookmarks.creators:
        if not creator.consolidation_path:
            continue
        albums = [lnk.name for lnk in creator.links if lnk.name]
        if not albums:
            continue
        res = consolidate_creator_files(creator.name, albums, source_base_dir, creator.consolidation_path)
        consolidations[creator.name] = res
        if res["success"]:
            total_ok += 1

    lines = [
        "",
        "[+] Consolidation Summary:",
        f"    Creators consolidated: {len(consolidations)}",
        f"    Successful: {total_ok}",
    ]
    for name, res in consolidations.items():
        lines.append(f"    {name}: {res['message']}")

    return {
        "total_creators": len(bookmarks.creators),
        "consolidations": consolidations,
        "summary": "\n".join(lines),
    }
