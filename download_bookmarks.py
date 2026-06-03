"""
Batch downloader for bookmarked URLs from bookmarks.yml
Reads creator links, downloads undownloaded content, and updates download status
"""
import yaml
import subprocess
import sys
import argparse
import os
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse
import consolidate


def load_bookmarks(filepath: str) -> dict:
    """Load bookmarks from YAML file"""
    with open(filepath, 'r') as f:
        return yaml.safe_load(f)


def save_bookmarks(filepath: str, data: dict) -> None:
    """Save bookmarks to YAML file with proper formatting"""
    with open(filepath, 'w') as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def normalize_bookmarks(bookmarks: dict) -> dict:
    """
    Normalize bookmarks to a consistent format.
    Supports both:
    - Traditional: links as dicts with 'name' and 'url' keys
    - Simplified: links as strings (just the URL)
    
    Returns a normalized bookmarks dict where all links are dicts with
    'name', 'url', and 'downloaded' keys.
    """
    creators = bookmarks.get('creators', [])
    
    for creator in creators:
        links = creator.get('links', [])
        normalized_links = []
        
        for i, link in enumerate(links):
            if isinstance(link, str):
                # Simplified format: just a URL string
                normalized_links.append({
                    'name': f'Link {i + 1}',
                    'url': link,
                    'downloaded': False
                })
            elif isinstance(link, dict):
                # Traditional format: dict with name/url (ensure all keys present)
                normalized_link = {
                    'name': link.get('name', f'Link {i + 1}'),
                    'url': link.get('url'),
                    'downloaded': link.get('downloaded', False)
                }
                normalized_links.append(normalized_link)
        
        creator['links'] = normalized_links
    
    return bookmarks


def download_url(url: str, extensions: str = None, custom_path: str = None, timeout: int = 300) -> tuple:
    """
    Download a single URL using dump.py
    Returns: (success: bool, created_folder_name: str or None)
    
    success: True if download succeeded, False otherwise
    created_folder_name: The actual album folder name created by dump.py (if successful), or None
    timeout: Maximum time in seconds to wait for download (default: 300)
    """
    try:
        download_dir = Path(custom_path) if custom_path else Path('downloads')
        
        # Get list of folders before download
        folders_before = set()
        if download_dir.exists():
            folders_before = {f.name for f in download_dir.iterdir() if f.is_dir()}
        
        # Build command with optional arguments
        # Note: dump.py uses -p for custom path, not -o
        cmd_parts = ['uv', 'run', 'dump.py', '-u', url]
        
        if extensions:
            cmd_parts.extend(['-e', extensions])
        
        if custom_path:
            cmd_parts.extend(['-p', custom_path])
        
        print(f"  Downloading: {url}")
        try:
            # Run without capturing output so child process stdout/stderr
            # (including tqdm progress bars) are shown live in the terminal.
            result = subprocess.run(cmd_parts, timeout=timeout)
        except subprocess.TimeoutExpired:
            print(f"    [-] Timeout: Download exceeded {timeout} seconds")
            return False, None

        if result.returncode != 0:
            print(f"    [-] Error: return code {result.returncode}")
            return False, None
        
        # Find newly created folder
        created_folder = None
        if download_dir.exists():
            folders_after = {f.name for f in download_dir.iterdir() if f.is_dir()}
            new_folders = folders_after - folders_before
            
            if new_folders:
                # Get the most recently modified folder
                created_folder = max(
                    [download_dir / folder for folder in new_folders],
                    key=lambda p: p.stat().st_mtime
                ).name
        
        return True, created_folder
    except Exception as e:
        print(f"  [-] Error downloading {url}: {e}")
        return False, None


def _sanitize_name(name: str) -> str:
    # mimic dump.remove_illegal_chars
    import re
    if name is None:
        return ''
    return re.sub(r'[<>:"/\\|?*\']|[\0-\31]', "-", name).strip()


def is_already_downloaded(url: str, download_path: str = None, link_name: str = None) -> bool:
    """Check if URL or album (via link_name) is already downloaded.
    - Checks already_downloaded.txt files for the URL
    - Checks for files matching URL basename in creator folders
    - If `link_name` provided, also checks for an album folder matching that name (tolerant match)
    """
    if download_path is None:
        download_path = "downloads"
    
    # Check in the main downloads directory
    main_check = Path(download_path) / "already_downloaded.txt"
    if main_check.exists():
        with open(main_check, 'r') as f:
            if url in f.read():
                return True
    
    # Check in creator subdirectories
    downloads_dir = Path(download_path)
    basename = os.path.basename(urlparse(url).path)
    if downloads_dir.exists():
        for creator_dir in downloads_dir.iterdir():
            if creator_dir.is_dir():
                # If link_name provided, check for matching album folder inside this creator_dir
                if link_name:
                    target_folder = creator_dir / link_name
                    # tolerant match: try sanitized and case-insensitive
                    sanitized = _sanitize_name(link_name)
                    alt_folder = creator_dir / sanitized
                    if target_folder.exists() or alt_folder.exists():
                        folder = target_folder if target_folder.exists() else alt_folder
                        # consider folder with any files as already downloaded
                        if any(folder.iterdir()):
                            return True

                check_file = creator_dir / "already_downloaded.txt"
                if check_file.exists():
                    with open(check_file, 'r', encoding='utf-8') as f:
                        if url in f.read():
                            return True

                # Also check for an existing file matching the URL's basename
                for item in creator_dir.iterdir():
                    if item.is_file() and item.name == basename:
                        return True

    return False



def main():
    parser = argparse.ArgumentParser(
        description="Batch download from bookmarks.yml"
    )
    parser.add_argument(
        '-b', '--bookmarks',
        default='bookmarks.yml',
        help='Path to bookmarks.yml file (default: bookmarks.yml)'
    )
    parser.add_argument(
        '-c', '--creator',
        nargs='+',
        help='Download only specific creator(s) by name (space-separated: -c Creator1 Creator2)'
    )
    parser.add_argument(
        '-e', '--extensions',
        help='File extensions to download (comma-separated, e.g., jpg,png,mp4)'
    )
    parser.add_argument(
        '-o', '--output',
        default='downloads',
        help='Output directory for downloads (default: downloads)'
    )
    parser.add_argument(
        '--skip-downloaded',
        action='store_true',
        help='Skip URLs that are already downloaded'
    )
    parser.add_argument(
        '--no-update',
        action='store_true',
        help='Do not update the bookmarks.yml file with download status'
    )
    parser.add_argument(
        '--timeout',
        type=int,
        default=300,
        help='Timeout in seconds for each download (default: 300)'
    )
    parser.add_argument(
        '--consolidate',
        action='store_true',
        help='Consolidate downloaded files to creator consolidation paths after download'
    )
    
    args = parser.parse_args()
    
    # Load bookmarks
    try:
        bookmarks = load_bookmarks(args.bookmarks)
    except FileNotFoundError:
        print(f"[-] Bookmarks file not found: {args.bookmarks}")
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"[-] Error parsing YAML: {e}")
        sys.exit(1)
    
    # Normalize bookmarks to consistent format
    bookmarks = normalize_bookmarks(bookmarks)
    
    print(f"[+] Loaded bookmarks from {args.bookmarks}")
    print(f"[+] Starting batch download at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    creators = bookmarks.get('creators', [])
    total_urls = sum(len(c.get('links', [])) for c in creators)
    downloaded_count = 0
    skipped_count = 0
    
    # Convert requested creators to lowercase for case-insensitive matching
    requested_creators = None
    if args.creator:
        requested_creators = [c.lower() for c in args.creator]
    
    for creator in creators:
        creator_name = creator.get('name', 'Unknown')
        
        # Skip if filtering by creator
        if requested_creators and creator_name.lower() not in requested_creators:
            continue
        
        links = creator.get('links', [])
        if not links:
            continue
        
        print(f"[*] Creator: {creator_name}")
        
        for link in links:
            url = link.get('url')
            link_name = link.get('name', 'Unknown')
            
            if not url:
                print(f"  [-] No URL found for {link_name}")
                continue

            # Honor bookmarks.yml flag first
            if args.skip_downloaded and link.get('downloaded'):
                print(f"  [~] Already downloaded (bookmarks): {link_name}")
                link['downloaded'] = True
                skipped_count += 1
                continue

            # Check filesystem / already_downloaded lists
            if args.skip_downloaded and is_already_downloaded(url, args.output, link_name):
                print(f"  [~] Already downloaded: {link_name}")
                link['downloaded'] = True
                skipped_count += 1
                continue
            
            # Download the URL
            success, created_folder = download_url(url, args.extensions, args.output, timeout=args.timeout)
            if success:
                link['downloaded'] = True
                downloaded_count += 1
                
                # Update link name to the actual folder name created by bunkr
                if created_folder and link.get('name', '').startswith('Link '):
                    old_name = link.get('name')
                    link['name'] = created_folder
                    print(f"    [+] Renamed '{old_name}' → '{created_folder}'")
            else:
                link['downloaded'] = False
        
        print()
    
    # Update bookmarks file if requested
    if not args.no_update:
        save_bookmarks(args.bookmarks, bookmarks)
        print(f"[+] Updated {args.bookmarks} with download status")
    
    print(f"\n[+] Batch download completed!")
    print(f"    Total URLs: {total_urls}")
    print(f"    Downloaded: {downloaded_count}")
    print(f"    Skipped: {skipped_count}")
    print(f"    Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Perform consolidation if requested
    if args.consolidate:
        print("\n[*] Starting file consolidation...")
        consolidation_result = consolidate.consolidate_from_bookmarks(bookmarks, args.output)
        print(consolidation_result['summary'])
        
        # Print detailed results for each creator
        for creator_name, result in consolidation_result['consolidations'].items():
            if result['files_moved'] > 0 or result['duplicates_renamed'] > 0:
                print(f"\n    {creator_name}:")
                print(f"      - Files moved: {result['files_moved']}")
                print(f"      - Duplicates renamed: {result['duplicates_renamed']}")
            if result['errors']:
                for error in result['errors']:
                    print(f"      [!] {error}")


if __name__ == "__main__":
    main()
