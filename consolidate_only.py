"""
Consolidation-only script.
Moves downloaded files to creator consolidation paths without downloading.
"""

import yaml
import sys
import argparse
from pathlib import Path
from datetime import datetime
import consolidate
from download_bookmarks import load_bookmarks, normalize_bookmarks


def main():
    parser = argparse.ArgumentParser(
        description="Consolidate downloaded files to creator consolidation paths (no downloads)"
    )
    parser.add_argument(
        '-b', '--bookmarks',
        default='bookmarks.yml',
        help='Path to bookmarks.yml file (default: bookmarks.yml)'
    )
    parser.add_argument(
        '-c', '--creator',
        nargs='+',
        help='Consolidate only specific creator(s) by name (space-separated: -c Creator1 Creator2)'
    )
    parser.add_argument(
        '-o', '--output',
        default='downloads',
        help='Output directory for downloads (where source files are located) (default: downloads)'
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
    print(f"[+] Starting consolidation at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    creators = bookmarks.get('creators', [])
    
    # Convert requested creators to lowercase for case-insensitive matching
    requested_creators = None
    if args.creator:
        requested_creators = [c.lower() for c in args.creator]
    
    # Filter creators if requested
    creators_to_consolidate = []
    for creator in creators:
        creator_name = creator.get('name', 'Unknown')
        
        # Skip if filtering by creator
        if requested_creators and creator_name.lower() not in requested_creators:
            continue
        
        # Skip if no consolidation_path defined
        if not creator.get('consolidation_path'):
            continue
        
        creators_to_consolidate.append(creator)
    
    # If no creators to consolidate, exit early
    if not creators_to_consolidate:
        if requested_creators:
            print(f"[-] No creators found with consolidation_path: {', '.join(args.creator)}")
        else:
            print("[-] No creators have consolidation_path defined in bookmarks")
        sys.exit(1)
    
    # Update bookmarks to only include creators we're consolidating
    bookmarks['creators'] = creators_to_consolidate
    
    # Run consolidation
    print(f"[*] Consolidating {len(creators_to_consolidate)} creator(s)...\n")
    consolidation_result = consolidate.consolidate_from_bookmarks(bookmarks, args.output)
    print(consolidation_result['summary'])
    
    # Print detailed results for each creator
    for creator_name, result in consolidation_result['consolidations'].items():
        if result['files_moved'] > 0 or result['duplicates_renamed'] > 0 or result['errors']:
            print(f"\n    {creator_name}:")
            if result['files_moved'] > 0:
                print(f"      - Files moved: {result['files_moved']}")
            if result['duplicates_renamed'] > 0:
                print(f"      - Duplicates renamed: {result['duplicates_renamed']}")
            if result['errors']:
                for error in result['errors']:
                    print(f"      [!] {error}")
            else:
                print(f"      - Status: ✓ Success")
    
    print(f"\n[+] Consolidation completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
