#!/usr/bin/env bash
# Example commands — replace URLs and creator names with your own.

# Download a single album
uv run cyberdrop download -u https://bunkr.cr/a/kRupjUVJ

# Download all bookmarks
uv run cyberdrop bookmarks

# Download specific creator(s)
uv run cyberdrop bookmarks -c Creator1

# Skip already-downloaded files
uv run cyberdrop bookmarks --skip-downloaded

# Filter by file extensions
uv run cyberdrop bookmarks -e jpg,png,mp4

# Custom output directory
uv run cyberdrop bookmarks -o ./my_downloads

# Preview without updating bookmarks.yml
uv run cyberdrop bookmarks --no-update

# Import URLs for a creator (paste URLs, then press Ctrl+Z+Enter on Windows or Ctrl+D on Mac/Linux)
uv run cyberdrop import -c "Creator2"
# Paste: https://bunkr.cr/a/url1
#        https://bunkr.cr/a/url2
#        https://bunkr.cr/a/url3
# → Adds 3 links as "Creator2 1", "Creator2 2", "Creator2 3"

# Download creator and consolidate to consolidation_path from bookmarks.yml
uv run cyberdrop bookmarks -c "Creator2" --consolidate

# Move already-downloaded files to consolidation paths (no re-download)
uv run cyberdrop consolidate

# Consolidate specific creators only
uv run cyberdrop consolidate -c Creator1 Creator3

# Download and consolidate multiple creators
uv run cyberdrop bookmarks -c Creator1 Creator2 Creator3 --consolidate
