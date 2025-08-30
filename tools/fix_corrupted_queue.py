#!/usr/bin/env python3
"""
Tool to fix corrupted queue state JSON files.

This tool attempts to repair corrupted new_queue_state.json files by:
1. Identifying the corruption point
2. Attempting to fix common JSON syntax errors
3. Recovering as much data as possible
4. Creating a repaired version of the file
"""

import json
import re
import sys
from pathlib import Path
from typing import Dict, Any, Optional, List


class QueueJSONRepairer:
    """Repairs corrupted queue JSON files."""
    
    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self.original_content = ""
        self.repaired_content = ""
        
    def load_file(self) -> bool:
        """Load the corrupted file content."""
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                self.original_content = f.read()
            print(f"Loaded file: {self.file_path} ({len(self.original_content)} characters)")
            return True
        except Exception as e:
            print(f"Error loading file: {e}")
            return False
    
    def identify_corruption_point(self) -> Optional[int]:
        """Try to identify where the JSON corruption starts."""
        try:
            json.loads(self.original_content)
            print("File is not corrupted - JSON is valid")
            return None
        except json.JSONDecodeError as e:
            print(f"JSON corruption detected at position {e.pos}: {e.msg}")
            return e.pos
    
    def attempt_basic_repairs(self) -> str:
        """Attempt basic JSON repairs."""
        content = self.original_content
        
        # Common repairs
        repairs_made = []
        
        # 1. Fix missing quotes around keys
        # Look for patterns like: key: value instead of "key": value
        key_pattern = r'(\s+)([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*'
        matches = re.findall(key_pattern, content)
        if matches:
            content = re.sub(key_pattern, r'\1"\2": ', content)
            repairs_made.append("Fixed unquoted keys")
        
        # 2. Fix trailing commas before closing brackets/braces
        content = re.sub(r',(\s*[}\]])', r'\1', content)
        if ',}' in self.original_content or ',]' in self.original_content:
            repairs_made.append("Removed trailing commas")
        
        # 3. Fix missing commas between objects/arrays
        # This is more complex and risky, so we'll be conservative
        
        # 4. Fix incomplete strings (missing closing quotes)
        # Look for strings that start with quote but don't end properly
        
        if repairs_made:
            print(f"Basic repairs attempted: {', '.join(repairs_made)}")
        
        return content
    
    def find_safe_truncation_point(self) -> int:
        """Find a safe point to truncate the JSON by working backwards from corruption."""
        content = self.original_content
        
        # Start from the end and work backwards in larger chunks for efficiency
        print("Searching for safe truncation point...")
        
        # Try to find the last occurrence of complete JSON structures
        # Look for patterns like "}," or "}]" or "}}" that indicate complete objects
        
        # Work backwards from the corruption point in 10KB chunks
        corruption_pos = self.identify_corruption_point()
        if not corruption_pos:
            return 0
            
        for start_pos in range(min(corruption_pos, len(content)), 0, -10000):
            chunk_start = max(0, start_pos - 10000)
            chunk = content[chunk_start:start_pos]
            
            # Look for complete JSON object endings
            for pattern in [r'}\s*,\s*"[^"]+"\s*:\s*{', r'}\s*}', r'}\s*]']:
                matches = list(re.finditer(pattern, chunk))
                if matches:
                    # Take the last match
                    last_match = matches[-1]
                    potential_end = chunk_start + last_match.start() + 1
                    
                    # Test if this creates valid JSON
                    test_content = content[:potential_end]
                    try:
                        json.loads(test_content)
                        print(f"Found safe truncation point at position {potential_end}")
                        return potential_end
                    except json.JSONDecodeError:
                        continue
            
            # Show progress
            if start_pos % 50000 == 0:
                print(f"Searching... position {start_pos}")
        
        print("No safe truncation point found")
        return 0
    
    def truncate_at_corruption(self, corruption_pos: int) -> str:
        """Truncate the file at the corruption point and try to close JSON properly."""
        # First try to find a safe truncation point
        safe_pos = self.find_safe_truncation_point()
        
        if safe_pos > 0:
            content = self.original_content[:safe_pos]
            print(f"Using safe truncation at position {safe_pos}")
            return content
        
        # Fallback: try to truncate at corruption point and fix
        content = self.original_content[:corruption_pos]
        
        # Try to close any open structures
        brace_count = 0
        bracket_count = 0
        in_string = False
        escape_next = False
        
        for char in content:
            if escape_next:
                escape_next = False
                continue
                
            if char == '\\':
                escape_next = True
                continue
                
            if char == '"' and not escape_next:
                in_string = not in_string
                continue
                
            if in_string:
                continue
                
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
            elif char == '[':
                bracket_count += 1
            elif char == ']':
                bracket_count -= 1
        
        # Close any open structures
        if in_string:
            content += '"'
        
        # Remove trailing comma if present
        content = content.rstrip().rstrip(',')
        
        # Close open brackets and braces
        content += ']' * bracket_count
        content += '}' * brace_count
        
        print(f"Truncated at corruption point {corruption_pos} and closed structures")
        return content
    
    def validate_json_structure(self, content: str) -> bool:
        """Validate that the JSON has the expected queue structure."""
        try:
            data = json.loads(content)
            
            # Check for expected queue structure
            required_keys = ['items', 'states', 'created_at']
            for key in required_keys:
                if key not in data:
                    print(f"Warning: Missing required key '{key}'")
                    return False
            
            # Validate items structure
            if not isinstance(data['items'], dict):
                print("Error: 'items' should be a dictionary")
                return False
            
            # Validate states structure
            if not isinstance(data['states'], dict):
                print("Error: 'states' should be a dictionary")
                return False
            
            print(f"Valid queue structure with {len(data['items'])} items and {len(data['states'])} states")
            return True
            
        except json.JSONDecodeError as e:
            print(f"JSON still invalid after repair: {e}")
            return False
    
    def extract_partial_data(self) -> Optional[Dict[str, Any]]:
        """Try to extract partial data from the corrupted file using regex."""
        content = self.original_content
        print("Attempting partial data extraction...")
        
        # Try to extract the main sections using regex
        items_data = {}
        states_data = {}
        created_at = "2025-01-01T00:00:00"
        
        # Extract created_at first (it's usually at the beginning)
        created_at_match = re.search(r'"created_at":\s*"([^"]*)"', content)
        if created_at_match:
            created_at = created_at_match.group(1)
            print(f"Found created_at: {created_at}")
        
        # Try to find and extract items section
        items_match = re.search(r'"items":\s*({[^}]*(?:{[^}]*}[^}]*)*})', content, re.DOTALL)
        if items_match:
            try:
                items_section = items_match.group(1)
                # Try to fix common issues in the items section
                items_section = re.sub(r',(\s*})', r'\1', items_section)  # Remove trailing commas
                items_data = json.loads(items_section)
                print(f"Extracted {len(items_data)} items")
            except json.JSONDecodeError as e:
                print(f"Failed to parse items section: {e}")
        
        # Try to find and extract states section
        states_match = re.search(r'"states":\s*({[^}]*(?:{[^}]*}[^}]*)*})', content, re.DOTALL)
        if states_match:
            try:
                states_section = states_match.group(1)
                # Try to fix common issues in the states section
                states_section = re.sub(r',(\s*})', r'\1', states_section)  # Remove trailing commas
                states_data = json.loads(states_section)
                print(f"Extracted {len(states_data)} states")
            except json.JSONDecodeError as e:
                print(f"Failed to parse states section: {e}")
        
        # If we couldn't extract with regex, try a simpler approach
        if not items_data and not states_data:
            print("Regex extraction failed, trying simple reconstruction...")
            # Create minimal valid structure
            return {
                "items": {},
                "states": {},
                "created_at": created_at
            }
        
        return {
            "items": items_data,
            "states": states_data,
            "created_at": created_at
        }
    
    def repair_file(self) -> bool:
        """Main repair function."""
        if not self.load_file():
            return False
        
        corruption_pos = self.identify_corruption_point()
        if corruption_pos is None:
            print("File is already valid JSON")
            return True
        
        print(f"\nAttempting repairs...")
        
        # Try basic repairs first
        repaired = self.attempt_basic_repairs()
        
        if self.validate_json_structure(repaired):
            self.repaired_content = repaired
            print("✓ Basic repairs successful!")
            return True
        
        # If basic repairs failed, try truncation
        print("Basic repairs failed, trying truncation...")
        repaired = self.truncate_at_corruption(corruption_pos)
        
        if repaired and self.validate_json_structure(repaired):
            self.repaired_content = repaired
            print("✓ Truncation and repair successful!")
            return True
        
        # If truncation failed, try partial data extraction
        print("Truncation failed, trying partial data extraction...")
        partial_data = self.extract_partial_data()
        
        if partial_data:
            self.repaired_content = json.dumps(partial_data, indent=2)
            if self.validate_json_structure(self.repaired_content):
                print("✓ Partial data extraction successful!")
                return True
        
        print("✗ Unable to repair the JSON file")
        return False
    
    def save_repaired_file(self, output_path: Optional[str] = None) -> bool:
        """Save the repaired content to a file."""
        if not self.repaired_content:
            print("No repaired content to save")
            return False
        
        if output_path is None:
            output_path = str(self.file_path.with_suffix('.repaired.json'))
        
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                # Pretty print the JSON
                data = json.loads(self.repaired_content)
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            print(f"✓ Repaired file saved to: {output_path}")
            return True
            
        except Exception as e:
            print(f"Error saving repaired file: {e}")
            return False
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about the repaired queue."""
        if not self.repaired_content:
            return {}
        
        try:
            data = json.loads(self.repaired_content)
            
            stats = {
                'total_items': len(data.get('items', {})),
                'total_states': len(data.get('states', {})),
                'created_at': data.get('created_at', 'Unknown'),
            }
            
            # Count by state
            state_counts = {}
            for state_data in data.get('states', {}).values():
                state = state_data.get('state', 'unknown')
                state_counts[state] = state_counts.get(state, 0) + 1
            
            stats['state_counts'] = state_counts
            
            return stats
            
        except Exception as e:
            print(f"Error getting statistics: {e}")
            return {}


def main():
    """Main function."""
    if len(sys.argv) != 2:
        print("Usage: python fix_corrupted_queue.py <path_to_corrupted_json>")
        print("Example: python fix_corrupted_queue.py \"C:\\Users\\HOME\\AppData\\Roaming\\DeeMusic\\new_queue_state.corrupted_20250813_182212.json\"")
        sys.exit(1)
    
    file_path = sys.argv[1]
    
    print(f"Queue JSON Repair Tool")
    print(f"=====================")
    print(f"Target file: {file_path}")
    print()
    
    repairer = QueueJSONRepairer(file_path)
    
    if repairer.repair_file():
        # Show statistics
        stats = repairer.get_statistics()
        if stats:
            print(f"\nRepaired Queue Statistics:")
            print(f"- Total items: {stats.get('total_items', 0)}")
            print(f"- Total states: {stats.get('total_states', 0)}")
            print(f"- Created at: {stats.get('created_at', 'Unknown')}")
            
            state_counts = stats.get('state_counts', {})
            if state_counts:
                print(f"- State breakdown:")
                for state, count in state_counts.items():
                    print(f"  - {state}: {count}")
        
        # Save repaired file
        if repairer.save_repaired_file():
            print(f"\n✓ Repair completed successfully!")
            print(f"You can now replace the original file with the repaired version.")
        else:
            print(f"\n✗ Failed to save repaired file")
            sys.exit(1)
    else:
        print(f"\n✗ Unable to repair the file")
        sys.exit(1)


if __name__ == "__main__":
    main()