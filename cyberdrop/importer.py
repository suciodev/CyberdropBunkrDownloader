"""
Bulk-import URLs into bookmarks.yml for a given creator.
Reads URLs from stdin, one per line.
"""

from __future__ import annotations

import sys
from urllib.parse import urlparse

from .bookmarks import Bookmarks


def validate_url(url: str) -> bool:
    try:
        p = urlparse(url.strip())
        return p.scheme in ("http", "https") and bool(p.netloc)
    except Exception:
        return False


def run_import(creator_name: str, bookmarks_path: str = "bookmarks.yml") -> None:
    bookmarks = Bookmarks.load(bookmarks_path)
    all_urls = {lnk.url for c in bookmarks.creators for lnk in c.links}

    print(f"[+] Importing URLs for creator: {creator_name}")
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
            if url in all_urls:
                print(f"  [~] Line {i}: already exists (skipped): {url}")
                dupes += 1
                continue
            lnk = bookmarks.add_link(creator_name, url)
            all_urls.add(url)
            print(f"  [+] Line {i}: added as {lnk.name!r}")
            imported += 1
    except KeyboardInterrupt:
        print("\n[!] Import cancelled")
        return
    except EOFError:
        pass

    if imported > 0:
        bookmarks.save(bookmarks_path)
        print(f"\n[+] Import complete — {imported} added, {dupes} skipped, {invalid} invalid")
        print(f"[+] Updated {bookmarks_path}")
    else:
        print(f"\n[!] No URLs imported (dupes: {dupes}, invalid: {invalid})")
