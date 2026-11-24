"""
scanner.py - Core Scanning and Duplicate Detection Module

This module is responsible for:
1. Scanning a folder and all its subfolders recursively.
2. Grouping files by size first to optimize performance.
3. Calculating SHA-256 cryptographic hashes to accurately detect duplicate files.
4. Structuring duplicate results into easy-to-read groups.
5. Safely deleting selected duplicate files while strictly preserving at least
   one original copy in every group and preventing path traversal attacks.
"""

import os
import hashlib
from pathlib import Path
from datetime import datetime


def format_file_size(size_in_bytes):
    """
    Convert a raw byte count into a readable string format (B, KB, MB, GB).
    
    Example:
        format_file_size(1048576) -> '1.00 MB'
    """
    if size_in_bytes < 0:
        return "0 B"
        
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(size_in_bytes)
    unit_index = 0
    
    while size >= 1024.0 and unit_index < len(units) - 1:
        size /= 1024.0
        unit_index += 1
        
    return f"{size:.2f} {units[unit_index]}"


def calculate_sha256(file_path, chunk_size=65536):
    """
    Calculate the SHA-256 hash of a file by reading it in chunks.
    
    Reading in chunks (64 KB) ensures large files do not exhaust system memory.
    If a file is locked or cannot be read, it returns None safely instead of crashing.
    """
    hasher = hashlib.sha256()
    
    try:
        with open(file_path, "rb") as file_handle:
            while True:
                chunk = file_handle.read(chunk_size)
                if not chunk:
                    break
                hasher.update(chunk)
        return hasher.hexdigest()
    except (PermissionError, OSError, FileNotFoundError):
        # File might be locked by another process or restricted by Windows permissions
        return None


def scan_for_duplicates(folder_path):
    """
    Scan a directory recursively and find all duplicate files.
    
    Process:
    1. Walk through the directory (skipping symlinks to avoid loops or path escape).
    2. Group files by exact byte size.
       - If only one file has a specific size, it CANNOT be a duplicate!
       - This saves substantial disk reads and CPU hashing time.
    3. For files sharing the same byte size, compute their SHA-256 hash.
    4. Group files with identical SHA-256 hashes.
    5. Organize duplicate groups, marking the first file (by oldest creation/mod time)
       as the original to keep, and the remaining as duplicate candidates.
    """
    # Verify the folder exists and is a valid directory
    base_path = Path(folder_path).resolve()
    if not base_path.exists() or not base_path.is_dir():
        return {
            "success": False,
            "error": "The specified folder does not exist or is not a valid directory."
        }

    total_scanned_files = 0
    size_map = {}  # Key: file size in bytes, Value: list of file path strings

    # Step 1: Walk the directory tree and group files by size
    # followlinks=False prevents following symbolic links outside the directory
    for root, _, files in os.walk(base_path, followlinks=False):
        for filename in files:
            file_full_path = os.path.join(root, filename)
            
            try:
                # Get file size in bytes
                file_stat = os.stat(file_full_path)
                file_size = file_stat.st_size
                
                # We track all scanned files
                total_scanned_files += 1
                
                # Group files by their exact byte size
                if file_size not in size_map:
                    size_map[file_size] = []
                size_map[file_size].append(file_full_path)
            except (PermissionError, OSError, FileNotFoundError):
                # Inaccessible file, skip safely
                continue

    # Step 2: Compare files with the same size using SHA-256 hashing
    hash_map = {}  # Key: sha256 hash, Value: list of file detail dicts

    for file_size, file_paths in size_map.items():
        # Optimization: Only calculate hashes if 2 or more files have the exact same size
        if len(file_paths) < 2:
            continue

        for file_path in file_paths:
            file_hash = calculate_sha256(file_path)
            
            # If the file couldn't be read, skip it
            if not file_hash:
                continue

            try:
                file_stat = os.stat(file_path)
                modified_timestamp = file_stat.st_mtime
                modified_date_str = datetime.fromtimestamp(modified_timestamp).strftime("%Y-%m-%d %H:%M:%S")
            except (OSError, PermissionError):
                modified_timestamp = 0
                modified_date_str = "Unknown"

            file_info = {
                "name": os.path.basename(file_path),
                "path": str(Path(file_path).resolve()),
                "size_bytes": file_size,
                "size_formatted": format_file_size(file_size),
                "modified_time": modified_date_str,
                "modified_timestamp": modified_timestamp,
                "is_original": False
            }

            if file_hash not in hash_map:
                hash_map[file_hash] = []
            hash_map[file_hash].append(file_info)

    # Step 3: Filter out hashes with only 1 file (no duplicates)
    duplicate_groups = []
    total_duplicate_files = 0
    total_wasted_bytes = 0
    group_counter = 1

    for file_hash, file_list in hash_map.items():
        if len(file_list) >= 2:
            # Sort files by modification date (oldest first) so the original is naturally first
            file_list.sort(key=lambda item: item["modified_timestamp"])
            
            # Mark the very first file as the original to preserve
            file_list[0]["is_original"] = True
            
            # Calculate wasted space for this group: (N - 1) * file_size
            file_size = file_list[0]["size_bytes"]
            group_wasted_bytes = (len(file_list) - 1) * file_size
            
            total_duplicate_files += (len(file_list) - 1)
            total_wasted_bytes += group_wasted_bytes

            duplicate_groups.append({
                "group_id": group_counter,
                "hash": file_hash,
                "file_count": len(file_list),
                "file_size_formatted": format_file_size(file_size),
                "wasted_bytes": group_wasted_bytes,
                "wasted_formatted": format_file_size(group_wasted_bytes),
                "files": file_list
            })
            group_counter += 1

    return {
        "success": True,
        "base_directory": str(base_path),
        "summary": {
            "total_scanned_files": total_scanned_files,
            "total_duplicate_groups": len(duplicate_groups),
            "total_duplicate_files": total_duplicate_files,
            "total_wasted_bytes": total_wasted_bytes,
            "total_wasted_formatted": format_file_size(total_wasted_bytes)
        },
        "groups": duplicate_groups
    }


def delete_selected_files(folder_path, files_to_delete, current_groups):
    """
    Safely delete requested duplicate files while enforcing strict safety rules:
    
    1. Folder Path Validation: Folder must exist.
    2. Path Traversal Prevention: Every file must reside strictly inside the scanned folder.
    3. Original Preservation Rule: NEVER delete the last remaining copy in any duplicate group.
    4. Permission / Locked File Handling: Catch OS and permission errors without stopping.
    """
    base_path = Path(folder_path).resolve()
    if not base_path.exists() or not base_path.is_dir():
        return {
            "success": False,
            "error": "The base folder is invalid or does not exist."
        }

    # Normalize paths requested for deletion
    requested_set = {str(Path(p).resolve()) for p in files_to_delete}
    
    if not requested_set:
        return {
            "success": False,
            "error": "No files were selected for deletion."
        }

    # Safety Rule 1: Validate against current groups to ensure at least one copy remains
    # Build a lookup of group_id -> list of file paths
    safe_to_delete = []
    blocked_files = []

    for group in current_groups:
        group_file_paths = [file_info["path"] for file_info in group.get("files", [])]
        
        # Files in this group that the user asked to delete
        marked_in_group = [p for p in group_file_paths if p in requested_set]
        
        # If the user marked ALL files in this group, protect at least one file!
        if len(marked_in_group) >= len(group_file_paths) and len(group_file_paths) > 0:
            # Preserve the original file (the first one)
            protected_file = group_file_paths[0]
            marked_in_group = [p for p in marked_in_group if p != protected_file]
            blocked_files.append({
                "path": protected_file,
                "reason": "Safety rule enforced: At least one original copy must be preserved."
            })
            
        safe_to_delete.extend(marked_in_group)

    deleted_count = 0
    freed_bytes = 0
    errors = []

    # Step 2: Delete each validated file
    for file_path_str in safe_to_delete:
        target_path = Path(file_path_str).resolve()

        # Security check: Prevent path traversal outside the base folder
        try:
            target_path.relative_to(base_path)
        except ValueError:
            errors.append({
                "path": file_path_str,
                "reason": "Access denied: Path is outside the scanned folder."
            })
            continue

        # Check if file actually exists and is a regular file (not directory or symlink)
        if not target_path.exists() or not target_path.is_file():
            errors.append({
                "path": file_path_str,
                "reason": "File does not exist or is not a regular file."
            })
            continue

        try:
            file_size = target_path.stat().st_size
            os.remove(target_path)
            deleted_count += 1
            freed_bytes += file_size
        except (PermissionError, OSError) as err:
            errors.append({
                "path": file_path_str,
                "reason": f"System error deleting file: {str(err)}"
            })

    return {
        "success": True,
        "deleted_count": deleted_count,
        "freed_bytes": freed_bytes,
        "freed_formatted": format_file_size(freed_bytes),
        "errors": errors,
        "blocked_files": blocked_files
    }

