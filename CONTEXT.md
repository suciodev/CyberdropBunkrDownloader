# Domain Model

## `Link`
A single bookmarked URL with a display name and download status flag.
Defined in `cyberdrop/bookmarks.py`.

## `Creator`
A content creator with a list of `Link`s and an optional `consolidation_path`.
The `consolidation_path` is the final directory where downloaded files are moved.
Defined in `cyberdrop/bookmarks.py`.

## `Bookmarks`
The full collection of `Creator`s loaded from `bookmarks.yml`.
Entry point for all bookmark I/O: `Bookmarks.load(path)` / `Bookmarks.save(path)`.
Defined in `cyberdrop/bookmarks.py`.

## `DownloadTracker`
Tracks which files have been downloaded, backed by `already_downloaded.txt` in an
album's output directory. Injectable into download functions for testing.
Defined in `cyberdrop/tracking.py`.
