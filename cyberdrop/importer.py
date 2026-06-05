"""
Bulk-import URLs into bookmarks.yml for a given creator.
Reads URLs from stdin, one per line.
"""

from __future__ import annotations

import sys
from urllib.parse import urlparse

from .bookmarks_io import load_bookmarks, save_bookmarks


def validate_url(url: str) -> bool:
    try:
        p = urlparse(url.strip())
        return p.scheme in ("http", "https") and bool(p.netloc)
    except Exception:
        return False


def url_exists(creators: list, url: str) -> bool:
    for creator in creators:
        for link in creator.get("links", []):
            existing = link.get("url") if isinstance(link, dict) else link
            if existing == url:
                return True
    return False


def find_or_create_creator(creators: list, name: str) -> dict:
    for c in creators:
        if c.get("name", "").lower() == name.lower():
            return c
    new = {"name": name, "links": []}
    creators.append(new)
    return new


def run_import(creator_name: str, bookmarks_path: str = "bookmarks.yml") -> None:
    bookmarks = load_bookmarks(bookmarks_path)
    creators = bookmarks.get("creators", [])
    creator = find_or_create_creator(creators, creator_name)

    print(f"[+] Importing URLs for creator: {creator['name']}")
    print("[*] Paste URLs (one per line), then press Ctrl+Z+Enter (Windows) or Ctrl+D (Mac/Linux) to finish:")
    print()

    imported = dupes = invalid = 0
    try:
        for i, line in enumerate(sys.stdin, 1):
            url = line.strip()
            if not url:
                continue
            if not validate_url(url):
                print(f"  [-] Line {i}: invalid URL: {url}")
                invalid += 1
                continue
            if url_exists(creators, url):
                print(f"  [~] Line {i}: already exists (skipped): {url}")
                dupes += 1
                continue
            link_number = len(creator.get("links", [])) + 1
            name = f"{creator['name']} {link_number}"
            creator["links"].append({"name": name, "url": url, "downloaded": False})
            print(f"  [+] Line {i}: added as {name!r}")
            imported += 1
    except KeyboardInterrupt:
        print("\n[!] Import cancelled")
        return
    except EOFError:
        pass

    if imported > 0:
        save_bookmarks(bookmarks_path, bookmarks)
        print(f"\n[+] Import complete — {imported} added, {dupes} skipped, {invalid} invalid")
        print(f"[+] Updated {bookmarks_path}")
    else:
        print(f"\n[!] No URLs imported (dupes: {dupes}, invalid: {invalid})")
