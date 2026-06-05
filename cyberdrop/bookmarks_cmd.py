"""
Batch download command: iterate bookmarks.yml and download undownloaded links.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

from .bookmarks_io import load_bookmarks, normalize_bookmarks, sanitize_filename, save_bookmarks
from .consolidate import consolidate_from_bookmarks
from .download import download_album


def is_already_downloaded(url: str, download_path: str = "downloads", link_name: str | None = None) -> bool:
    """Return True if the URL has been tracked in any already_downloaded.txt or a matching folder exists."""
    dl_dir = Path(download_path)

    top_tracker = dl_dir / "already_downloaded.txt"
    if top_tracker.exists() and url in top_tracker.read_text(encoding="utf-8"):
        return True

    if not dl_dir.exists():
        return False

    basename = os.path.basename(url.split("?")[0])
    for sub in dl_dir.iterdir():
        if not sub.is_dir():
            continue

        if link_name:
            for candidate in (sub / link_name, sub / sanitize_filename(link_name)):
                if candidate.exists() and any(candidate.iterdir()):
                    return True

        tracker = sub / "already_downloaded.txt"
        if tracker.exists() and url in tracker.read_text(encoding="utf-8"):
            return True

        if any(f.name == basename for f in sub.iterdir() if f.is_file()):
            return True

    return False


def run_bookmarks(
    bookmarks_path: str = "bookmarks.yml",
    creators_filter: list[str] | None = None,
    extensions: str | None = None,
    output_dir: str = "downloads",
    skip_downloaded: bool = False,
    no_update: bool = False,
    consolidate: bool = False,
) -> None:
    if not Path(bookmarks_path).exists():
        print(f"[-] Bookmarks file not found: {bookmarks_path}")
        sys.exit(1)
    bookmarks = load_bookmarks(bookmarks_path)

    bookmarks = normalize_bookmarks(bookmarks)
    print(f"[+] Loaded bookmarks from {bookmarks_path}")
    print(f"[+] Starting batch download at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    creators = bookmarks.get("creators", [])
    lower_filter = {c.lower() for c in creators_filter} if creators_filter else None
    downloaded_count = skipped_count = 0

    for creator in creators:
        creator_name = creator.get("name", "Unknown")
        if lower_filter and creator_name.lower() not in lower_filter:
            continue

        links = creator.get("links", [])
        if not links:
            continue

        print(f"[*] Creator: {creator_name}")

        for link in links:
            url = link.get("url")
            link_name = link.get("name", "Unknown")

            if not url:
                print(f"  [-] No URL for {link_name!r}")
                continue

            if skip_downloaded and link.get("downloaded"):
                print(f"  [~] Already downloaded (bookmarks flag): {link_name}")
                skipped_count += 1
                continue

            if skip_downloaded and is_already_downloaded(url, output_dir, link_name):
                print(f"  [~] Already downloaded (filesystem): {link_name}")
                link["downloaded"] = True
                skipped_count += 1
                continue

            print(f"  Downloading: {url}")
            result = download_album(url, extensions=extensions, output_dir=output_dir)

            if result.success:
                link["downloaded"] = True
                downloaded_count += 1
                if result.folder_name and (
                    link_name.startswith("Link ") or link_name.startswith(f"{creator_name} ")
                ):
                    link["name"] = result.folder_name
                    print(f"    [+] Renamed {link_name!r} → {result.folder_name!r}")
            else:
                link["downloaded"] = False
                for err in result.errors:
                    print(f"    [-] {err}")

        print()

    if not no_update:
        save_bookmarks(bookmarks_path, bookmarks)
        print(f"[+] Updated {bookmarks_path}")

    total = sum(len(c.get("links", [])) for c in creators)
    print(f"\n[+] Batch download complete")
    print(f"    Total: {total} | Downloaded: {downloaded_count} | Skipped: {skipped_count}")
    print(f"    Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    if consolidate:
        print("\n[*] Starting file consolidation...")
        result = consolidate_from_bookmarks(bookmarks, output_dir)
        print(result["summary"])
        for name, res in result["consolidations"].items():
            if res["files_moved"] or res["duplicates_renamed"] or res["errors"]:
                print(f"\n    {name}:")
                if res["files_moved"]:
                    print(f"      Files moved: {res['files_moved']}")
                if res["duplicates_renamed"]:
                    print(f"      Duplicates renamed: {res['duplicates_renamed']}")
                for err in res["errors"]:
                    print(f"      [!] {err}")
