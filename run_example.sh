uv run dump.py -u https://bunkr.cr/a/kRupjUVJ

# Download all bookmarks
uv run download_bookmarks.py

# Download specific creator
uv run download_bookmarks.py -c Creator1

# Skip already downloaded files
uv run download_bookmarks.py --skip-downloaded

# Filter by file extensions
uv run download_bookmarks.py -e jpg,png,mp4

# Custom output directory
uv run download_bookmarks.py -o ./my_downloads

# Preview without updating bookmarks.yml
uv run download_bookmarks.py --no-update

uv run bulk_import.py -c "Creator2"
# Paste: https://bunkr.cr/a/url1
#        https://bunkr.cr/a/url2
#        https://bunkr.cr/a/url3
# → Creates 3 links as "Link 1", "Link 2", "Link 3"

# bookmarks.yml has: consolidation_path: E:\Media\Creator2
uv run download_bookmarks.py -c "Creator2" --consolidate
# → Downloads all Creator2 albums, then moves all files to E:\Media\Creator2

uv run download_bookmarks.py --consolidate --skip-downloaded
# → Just moves already-downloaded files to their consolidation paths

# Download and consolidate 3 creators
uv run download_bookmarks.py -c Creator1 Creator3 Creator2 --consolidate

# Case-insensitive (works too)
uv run download_bookmarks.py -c Creator1 Creator3 Creator2 --consolidate

# consolidate_only
uv run consolidate_only.py -c Creator1 Creator3