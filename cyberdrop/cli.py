"""
Entry point for the `cyberdrop` CLI.

Subcommands:
  download    Download a single album or file list directly
  bookmarks   Batch-download from bookmarks.yml
  import      Add URLs to bookmarks.yml (reads stdin)
  consolidate Move staged files to creator consolidation directories
"""

from __future__ import annotations

import argparse
import sys


def _date(value: str):
    from datetime import datetime
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid date {value!r} — use YYYY-MM-DDTHH:MM:SS")


def _cmd_download(args: argparse.Namespace) -> None:
    from .download import download_all

    sys.stdout.reconfigure(encoding="utf-8")

    if args.url:
        urls = [args.url]
    else:
        with open(args.file, "r", encoding="utf-8") as f:
            urls = [line.strip() for line in f if line.strip()]

    results = download_all(
        urls,
        extensions=args.extensions,
        output_dir=args.path or "downloads",
        export_urls=args.export_urls,
        date_before=args.before,
        date_after=args.after,
    )

    for result in results:
        if not result.success:
            for err in result.errors:
                print(f"\t[-] {err}")


def _cmd_bookmarks(args: argparse.Namespace) -> None:
    from .bookmarks_cmd import run_bookmarks
    sys.stdout.reconfigure(encoding="utf-8")
    run_bookmarks(
        bookmarks_path=args.bookmarks,
        creators_filter=args.creator,
        extensions=args.extensions,
        output_dir=args.output,
        skip_downloaded=args.skip_downloaded,
        no_update=args.no_update,
        consolidate=args.consolidate,
    )


def _cmd_import(args: argparse.Namespace) -> None:
    from .importer import run_import
    sys.stdout.reconfigure(encoding="utf-8")
    run_import(creator_name=args.creator, bookmarks_path=args.bookmarks)


def _cmd_consolidate(args: argparse.Namespace) -> None:
    from datetime import datetime
    from pathlib import Path

    from .bookmarks import Bookmarks
    from .consolidate import consolidate_from_bookmarks

    sys.stdout.reconfigure(encoding="utf-8")

    if not Path(args.bookmarks).exists():
        print(f"[-] Bookmarks file not found: {args.bookmarks}")
        sys.exit(1)
    bookmarks = Bookmarks.load(args.bookmarks)

    lower_filter = {c.lower() for c in args.creator} if args.creator else None
    if lower_filter:
        bookmarks.creators = [c for c in bookmarks.creators if c.name.lower() in lower_filter]

    creators_with_path = [c for c in bookmarks.creators if c.consolidation_path]
    if not creators_with_path:
        msg = (
            f"No creators matching {args.creator} have a consolidation_path"
            if args.creator
            else "No creators have a consolidation_path defined in bookmarks"
        )
        print(f"[-] {msg}")
        sys.exit(1)

    bookmarks.creators = creators_with_path
    print(f"[+] Loaded bookmarks from {args.bookmarks}")
    print(f"[+] Consolidating {len(creators_with_path)} creator(s)...\n")

    result = consolidate_from_bookmarks(bookmarks, args.output)
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
            if not res["errors"]:
                print("      Status: OK")

    print(f"\n[+] Consolidation completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cyberdrop",
        description="Download files from Bunkr and Cyberdrop albums.",
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    sub.required = True

    # ---- download ----
    dl = sub.add_parser("download", help="Download a single album or file list")
    src = dl.add_mutually_exclusive_group(required=True)
    src.add_argument("-u", "--url", help="Album or file URL")
    src.add_argument("-f", "--file", help="File containing URLs (one per line)")
    dl.add_argument("-e", "--extensions", help="Only download these extensions (comma-separated, e.g. jpg,mp4)")
    dl.add_argument("-p", "--path", help="Custom output directory (default: downloads/)")
    dl.add_argument("-w", "--export-urls", action="store_true", help="Write URL list instead of downloading")
    dl.add_argument("--before", type=_date, metavar="YYYY-MM-DDTHH:MM:SS", help="Only files uploaded before this date")
    dl.add_argument("--after", type=_date, metavar="YYYY-MM-DDTHH:MM:SS", help="Only files uploaded after this date")
    dl.set_defaults(func=_cmd_download)

    # ---- bookmarks ----
    bk = sub.add_parser("bookmarks", help="Batch-download from bookmarks.yml")
    bk.add_argument("-b", "--bookmarks", default="bookmarks.yml", help="Path to bookmarks file (default: bookmarks.yml)")
    bk.add_argument("-c", "--creator", nargs="+", metavar="NAME", help="Download only these creator(s)")
    bk.add_argument("-e", "--extensions", help="Only download these extensions (comma-separated)")
    bk.add_argument("-o", "--output", default="downloads", help="Download staging directory (default: downloads)")
    bk.add_argument("--skip-downloaded", action="store_true", help="Skip links already marked downloaded")
    bk.add_argument("--no-update", action="store_true", help="Don't update bookmarks.yml with new download status")
    bk.add_argument("--consolidate", action="store_true", help="Move files to consolidation_path after downloading")
    bk.set_defaults(func=_cmd_bookmarks)

    # ---- import ----
    imp = sub.add_parser("import", help="Add URLs from stdin to bookmarks.yml")
    imp.add_argument("-c", "--creator", required=True, metavar="NAME", help="Creator name to import URLs under")
    imp.add_argument("-b", "--bookmarks", default="bookmarks.yml", help="Path to bookmarks file (default: bookmarks.yml)")
    imp.set_defaults(func=_cmd_import)

    # ---- consolidate ----
    con = sub.add_parser("consolidate", help="Move staged downloads to creator consolidation directories")
    con.add_argument("-b", "--bookmarks", default="bookmarks.yml", help="Path to bookmarks file (default: bookmarks.yml)")
    con.add_argument("-c", "--creator", nargs="+", metavar="NAME", help="Consolidate only these creator(s)")
    con.add_argument("-o", "--output", default="downloads", help="Staging directory (where downloads are) (default: downloads)")
    con.set_defaults(func=_cmd_consolidate)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)
