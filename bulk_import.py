"""
Bulk import URLs into bookmarks.yml for a specific creator.

Usage:
    echo "https://bunkr.cr/a/URL1" | uv run bulk_import.py -c "CreatorName"
    Or paste multiple URLs (one per line) and EOF when done.

Features:
- Auto-generates placeholder names using creator name ("CreatorName 1", "CreatorName 2", etc.)
- Checks for duplicate URLs before adding
- Creates new creator entry if needed
- Validates URL format
"""

import sys
import yaml
import argparse
from pathlib import Path
from urllib.parse import urlparse


def load_bookmarks(filepath: str) -> dict:
    """Load bookmarks from YAML file, or return empty structure if not exists"""
    path = Path(filepath)
    if path.exists():
        with open(path, 'r') as f:
            data = yaml.safe_load(f)
            return data if data else {'creators': []}
    return {'creators': []}


def save_bookmarks(filepath: str, data: dict) -> None:
    """Save bookmarks to YAML file with proper formatting"""
    with open(filepath, 'w') as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def validate_url(url: str) -> bool:
    """Validate URL format (basic check for http/https)"""
    try:
        parsed = urlparse(url.strip())
        return parsed.scheme in ('http', 'https') and bool(parsed.netloc)
    except Exception:
        return False


def url_exists(creators: list, url: str) -> bool:
    """Check if URL already exists in any creator's links"""
    for creator in creators:
        for link in creator.get('links', []):
            if isinstance(link, dict) and link.get('url') == url:
                return True
            # Handle simplified format (URL-only string)
            elif isinstance(link, str) and link == url:
                return True
    return False


def find_or_create_creator(creators: list, creator_name: str) -> dict:
    """Find creator by name or create new entry"""
    for creator in creators:
        if creator.get('name', '').lower() == creator_name.lower():
            return creator
    
    # Create new creator
    new_creator = {
        'name': creator_name,
        'links': []
    }
    creators.append(new_creator)
    return new_creator


def get_next_link_number(creator: dict) -> int:
    """Get the next available link number for auto-naming"""
    return len(creator.get('links', [])) + 1


def main():
    parser = argparse.ArgumentParser(
        description='Bulk import URLs into bookmarks.yml'
    )
    parser.add_argument(
        '-c', '--creator',
        required=True,
        help='Creator name to import URLs for'
    )
    parser.add_argument(
        '-b', '--bookmarks',
        default='bookmarks.yml',
        help='Path to bookmarks.yml file (default: bookmarks.yml)'
    )
    parser.add_argument(
        '--auto-name',
        action='store_true',
        help='Use placeholder names (Link 1, Link 2, etc.) - default behavior'
    )
    
    args = parser.parse_args()
    
    # Load existing bookmarks
    bookmarks = load_bookmarks(args.bookmarks)
    creators = bookmarks.get('creators', [])
    
    # Find or create creator
    creator = find_or_create_creator(creators, args.creator)
    
    print(f"[+] Importing URLs for creator: {creator['name']}")
    print("[*] Enter URLs (one per line), then press Ctrl+D (Linux/Mac) or Ctrl+Z+Enter (Windows) to finish:")
    print()
    
    imported_count = 0
    duplicate_count = 0
    invalid_count = 0
    
    try:
        for line_num, line in enumerate(sys.stdin, 1):
            url = line.strip()
            
            # Skip empty lines
            if not url:
                continue
            
            # Validate URL format
            if not validate_url(url):
                print(f"  [-] Line {line_num}: Invalid URL format: {url}")
                invalid_count += 1
                continue
            
            # Check for duplicates
            if url_exists(creators, url):
                print(f"  [~] Line {line_num}: URL already exists (skipped): {url}")
                duplicate_count += 1
                continue
            
            # Generate placeholder name (includes creator name for fuzzy matching fallback)
            link_number = get_next_link_number(creator)
            placeholder_name = f"{creator['name']} {link_number}"
            
            # Add link to creator
            new_link = {
                'name': placeholder_name,
                'url': url,
                'downloaded': False
            }
            creator['links'].append(new_link)
            
            print(f"  [+] Line {line_num}: Added as '{placeholder_name}'")
            imported_count += 1
    
    except KeyboardInterrupt:
        print("\n[!] Import cancelled by user")
        return
    except EOFError:
        pass
    
    # Save if any URLs were imported
    if imported_count > 0:
        save_bookmarks(args.bookmarks, bookmarks)
        print()
        print(f"[+] Import completed!")
        print(f"    Imported: {imported_count}")
        print(f"    Duplicates skipped: {duplicate_count}")
        print(f"    Invalid URLs: {invalid_count}")
        print(f"[+] Updated {args.bookmarks}")
    else:
        print()
        print("[!] No valid URLs imported")
        if duplicate_count > 0:
            print(f"    Duplicates: {duplicate_count}")
        if invalid_count > 0:
            print(f"    Invalid: {invalid_count}")


if __name__ == "__main__":
    main()
