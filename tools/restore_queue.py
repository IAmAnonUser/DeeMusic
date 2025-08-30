#!/usr/bin/env python3
"""
Tool to restore a repaired queue file as the active queue.

This tool safely replaces the current queue file with a repaired version.
"""

import sys
import shutil
from pathlib import Path
from datetime import datetime


def main():
    """Main function."""
    if len(sys.argv) != 2:
        print("Usage: python restore_queue.py <path_to_repaired_json>")
        print("Example: python restore_queue.py \"C:\\Users\\HOME\\AppData\\Roaming\\DeeMusic\\new_queue_state.corrupted_20250813_182212.repaired.json\"")
        sys.exit(1)
    
    repaired_file = Path(sys.argv[1])
    
    if not repaired_file.exists():
        print(f"Error: Repaired file not found: {repaired_file}")
        sys.exit(1)
    
    # Determine the target queue file path
    app_data_dir = Path.home() / "AppData" / "Roaming" / "DeeMusic"
    target_file = app_data_dir / "new_queue_state.json"
    
    print(f"Queue Restoration Tool")
    print(f"=====================")
    print(f"Repaired file: {repaired_file}")
    print(f"Target file: {target_file}")
    print()
    
    # Create backup of current file if it exists
    if target_file.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = target_file.with_suffix(f'.backup_{timestamp}.json')
        
        try:
            shutil.copy2(target_file, backup_file)
            print(f"✓ Current queue backed up to: {backup_file}")
        except Exception as e:
            print(f"Warning: Could not create backup: {e}")
    
    # Copy repaired file to target location
    try:
        shutil.copy2(repaired_file, target_file)
        print(f"✓ Repaired queue restored to: {target_file}")
        print()
        print("The repaired queue is now active. You can start DeeMusic to use it.")
        
    except Exception as e:
        print(f"✗ Error restoring queue: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()