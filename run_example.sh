#!/usr/bin/env bash
# run_example.sh — hands-on tour of every cyberdrop command.
#
# Edit the values in the CONFIGURATION section below, then run:
#   bash run_example.sh
#
# Requires: uv (https://docs.astral.sh/uv/)
# Install deps first if you haven't: uv sync

set -euo pipefail

# ─────────────────────────────────────────────
# CONFIGURATION — edit these before running
# ─────────────────────────────────────────────
BUNKR_ALBUM="https://bunkr.cr/a/XXXXXXXX"          # a real bunkr album URL
CYBERDROP_ALBUM="https://cyberdrop.me/a/YYYYYYYY"  # a real cyberdrop album URL
CREATOR_NAME="ExampleCreator"                       # must match a name in bookmarks.yml
DOWNLOADS_DIR="./downloads"
# ─────────────────────────────────────────────

echo "=== 1. Download a single Bunkr album ==="
uv run cyberdrop download -u "$BUNKR_ALBUM"

echo
echo "=== 2. Download a single Cyberdrop album ==="
uv run cyberdrop download -u "$CYBERDROP_ALBUM"

echo
echo "=== 3. Download only images from an album ==="
uv run cyberdrop download -u "$BUNKR_ALBUM" -e jpg,png,webp

echo
echo "=== 4. Download to a custom output directory ==="
uv run cyberdrop download -u "$BUNKR_ALBUM" -p ./my_downloads

echo
echo "=== 5. Export URL list instead of downloading (for wget/aria2c) ==="
uv run cyberdrop download -u "$BUNKR_ALBUM" -w

echo
echo "=== 6. Download only files uploaded before a date ==="
uv run cyberdrop download -u "$BUNKR_ALBUM" --before 2025-01-01T00:00:00

echo
echo "=== 7. Batch-download everything in bookmarks.yml ==="
uv run cyberdrop bookmarks

echo
echo "=== 8. Download a specific creator only ==="
uv run cyberdrop bookmarks -c "$CREATOR_NAME"

echo
echo "=== 9. Download multiple creators ==="
uv run cyberdrop bookmarks -c "$CREATOR_NAME" AnotherCreator

echo
echo "=== 10. Skip albums already marked as downloaded ==="
uv run cyberdrop bookmarks --skip-downloaded

echo
echo "=== 11. Filter by extension across all bookmarks ==="
uv run cyberdrop bookmarks -e mp4,mov

echo
echo "=== 12. Preview run — don't update bookmarks.yml with status ==="
uv run cyberdrop bookmarks --no-update

echo
echo "=== 13. Download + move files to consolidation_path in one step ==="
uv run cyberdrop bookmarks -c "$CREATOR_NAME" --consolidate

echo
echo "=== 14. Import URLs from stdin into bookmarks.yml ==="
echo "    Paste URLs one per line, then Ctrl+D (Mac/Linux) or Ctrl+Z+Enter (Windows)"
echo "    Example (pipe-mode — skip if running interactively):"
printf '%s\n%s\n' "$BUNKR_ALBUM" "$CYBERDROP_ALBUM" | uv run cyberdrop import -c "$CREATOR_NAME"

echo
echo "=== 15. Move already-downloaded files to consolidation paths ==="
echo "    (no re-download; consolidation_path must be set in bookmarks.yml)"
uv run cyberdrop consolidate

echo
echo "=== 16. Consolidate specific creators only ==="
uv run cyberdrop consolidate -c "$CREATOR_NAME"

echo
echo "=== 17. Consolidate from a non-default staging directory ==="
uv run cyberdrop consolidate -o "$DOWNLOADS_DIR"

echo
echo "Done."
