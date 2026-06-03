"""
File consolidation module for organizing downloaded files.
Moves downloaded files from album folders into a consolidation directory per creator.
Automatically handles duplicate filenames by renaming.
"""

import os
import shutil
from pathlib import Path
from typing import Optional, Dict, List, Tuple
import re


def _normalize_name(name: str) -> str:
    """
    Normalize a name by removing special characters and converting to lowercase.
    Used for fuzzy matching creator/album names.
    Example: "John Smith" -> "johnsmith"
    """
    if not name:
        return ""
    # Remove special characters and spaces, convert to lowercase
    normalized = re.sub(r'[^a-z0-9]', '', name.lower())
    return normalized


def _folder_matches_creator(folder_name: str, creator_name: str) -> bool:
    """
    Check if a folder name matches the creator name (fuzzy matching).
    """
    folder_normalized = _normalize_name(folder_name)
    creator_normalized = _normalize_name(creator_name)
    
    # Exact normalized match
    if folder_normalized == creator_normalized:
        return True
    
    # Check if all parts of creator name appear in folder name
    # Split the ORIGINAL creator name by spaces and special chars, then check if all parts are in folder
    creator_parts = [p.lower() for p in re.split(r'[^a-z]+', creator_name) if p]
    
    if creator_parts:
        # For "John Smith", creator_parts = ["john", "smith"]
        # Check if all these parts appear (as substrings) in the folder name
        all_parts_in_folder = all(part in folder_normalized for part in creator_parts)
        if all_parts_in_folder:
            return True
    
    return False


def _get_unique_filename(target_dir: Path, filename: str) -> str:
    """
    Generate a unique filename for a file that might already exist in target_dir.
    If file doesn't exist, returns the original filename.
    If file exists, appends a numeric suffix before the extension (e.g., file_1.txt, file_2.txt).
    """
    target_path = target_dir / filename
    
    if not target_path.exists():
        return filename
    
    # Split filename into name and extension
    name_parts = filename.rsplit('.', 1)
    if len(name_parts) == 2:
        name, ext = name_parts
        extension = f".{ext}"
    else:
        name = filename
        extension = ""
    
    # Find the next available number
    counter = 1
    while True:
        new_filename = f"{name}_{counter}{extension}"
        if not (target_dir / new_filename).exists():
            return new_filename
        counter += 1


def consolidate_creator_files(
    creator_name: str,
    album_names: List[str],
    source_base_dir: str,
    target_dir: str
) -> Dict[str, any]:
    """
    Consolidate downloaded files for a creator from their specific album folders
    into a target consolidation directory.
    
    Args:
        creator_name: Name of the creator (for logging/context only)
        album_names: List of album folder names that belong to this creator
                    (these should match the 'name' field in bookmarks links)
        source_base_dir: Base directory containing all album folders (e.g., 'downloads')
        target_dir: Target consolidation directory (absolute or relative path)
    
    Returns:
        A dictionary with consolidation statistics:
        {
            'success': bool,
            'files_moved': int,
            'duplicates_renamed': int,
            'files_skipped': List[str],
            'errors': List[str],
            'message': str
        }
    """
    
    result = {
        'success': False,
        'files_moved': 0,
        'duplicates_renamed': 0,
        'files_skipped': [],
        'errors': [],
        'message': ''
    }
    
    source_base = Path(source_base_dir)
    target_path = Path(target_dir)
    
    # Validate source directory
    if not source_base.exists():
        result['errors'].append(f"Source directory not found: {source_base}")
        result['message'] = f"[-] Source directory not found: {source_base}"
        return result
    
    # Create target directory if it doesn't exist
    try:
        target_path.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        result['errors'].append(f"Failed to create target directory: {e}")
        result['message'] = f"[-] Failed to create target directory: {e}"
        return result
    
    files_moved = 0
    duplicates_renamed = 0
    files_skipped = []
    errors = []
    
    # Track which folders have been processed to avoid duplicates
    processed_folders = set()
    
    # Step 1: Process explicit album folders from bookmarks
    for album_name in album_names:
        album_dir = source_base / album_name
        
        if album_dir.exists() and album_dir.is_dir():
            processed_folders.add(album_dir.name)
            # Move files from this album
            fm, dr, fs, er = _move_files_from_folder(album_dir, target_path)
            files_moved += fm
            duplicates_renamed += dr
            files_skipped.extend(fs)
            errors.extend(er)
    
    # Step 2: Also look for folders that match the creator name (fuzzy matching)
    # This handles cases where auto-rename didn't run or folder names don't match exactly
    if source_base.exists():
        for item in source_base.iterdir():
            if item.is_dir() and item.name not in processed_folders:
                # Check if this folder matches the creator name
                if _folder_matches_creator(item.name, creator_name):
                    processed_folders.add(item.name)
                    # Move files from this folder
                    fm, dr, fs, er = _move_files_from_folder(item, target_path)
                    files_moved += fm
                    duplicates_renamed += dr
                    files_skipped.extend(fs)
                    errors.extend(er)
    
    # Build result
    result['success'] = len(errors) == 0
    result['files_moved'] = files_moved
    result['duplicates_renamed'] = duplicates_renamed
    result['files_skipped'] = files_skipped
    result['errors'] = errors
    
    if result['success']:
        result['message'] = (
            f"[+] Consolidation successful: "
            f"{files_moved} files moved, {duplicates_renamed} duplicates renamed"
        )
    else:
        result['message'] = (
            f"[!] Consolidation completed with errors: "
            f"{files_moved} files moved, {len(errors)} errors"
        )
    
    return result


def _move_files_from_folder(folder_path: Path, target_dir: Path) -> Tuple[int, int, List[str], List[str]]:
    """
    Helper function to move files from a folder to target directory.
    
    Returns: (files_moved, duplicates_renamed, files_skipped, errors)
    """
    files_moved = 0
    duplicates_renamed = 0
    files_skipped = []
    errors = []
    
    # Iterate through files in this album directory
    for item in folder_path.iterdir():
        # Skip already_downloaded.txt and directories
        if item.name.lower() == 'already_downloaded.txt' or item.is_dir():
            files_skipped.append(item.name)
            continue
        
        # Move file to target directory
        try:
            unique_name = _get_unique_filename(target_dir, item.name)
            target_file = target_dir / unique_name
            
            # Track if this was a rename due to duplicate
            if unique_name != item.name:
                duplicates_renamed += 1
            
            shutil.move(str(item), str(target_file))
            files_moved += 1
        
        except Exception as e:
            error_msg = f"Failed to move {item.name}: {e}"
            errors.append(error_msg)
    
    return files_moved, duplicates_renamed, files_skipped, errors


def consolidate_from_bookmarks(
    bookmarks: dict,
    source_base_dir: str = 'downloads'
) -> Dict[str, any]:
    """
    Consolidate files for all creators that have a consolidation_path defined.
    
    Args:
        bookmarks: Loaded and normalized bookmarks dict
        source_base_dir: Base directory for downloads
    
    Returns:
        Dictionary with consolidation results for each creator:
        {
            'total_creators': int,
            'consolidations': {
                'creator_name': {consolidate_creator_files result}
            },
            'summary': str
        }
    """
    
    creators = bookmarks.get('creators', [])
    consolidations = {}
    total_consolidated = 0
    
    for creator in creators:
        creator_name = creator.get('name', 'Unknown')
        consolidation_path = creator.get('consolidation_path')
        
        # Skip if no consolidation_path defined
        if not consolidation_path:
            continue
        
        # Get album names (link names) for this creator
        links = creator.get('links', [])
        album_names = [link.get('name') for link in links if link.get('name')]
        
        # Skip if no albums to consolidate
        if not album_names:
            continue
        
        # Perform consolidation
        result = consolidate_creator_files(
            creator_name,
            album_names,
            source_base_dir,
            consolidation_path
        )
        
        consolidations[creator_name] = result
        if result['success']:
            total_consolidated += 1
    
    # Build summary
    summary = (
        f"\n[+] Consolidation Summary:\n"
        f"    Creators with consolidation: {len(consolidations)}\n"
        f"    Successful: {total_consolidated}\n"
    )
    
    for creator_name, result in consolidations.items():
        summary += f"    {creator_name}: {result['message']}\n"
    
    return {
        'total_creators': len(creators),
        'consolidations': consolidations,
        'summary': summary
    }
