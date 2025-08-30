"""
Configuration management for DeeMusic Library Scanner
"""

import os
import json
import logging
import sys
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)

class Config:
    """Configuration manager for the Library Scanner application."""
    
    def __init__(self):
        """Initialize configuration with default values."""
        # Use %appdata%/DeeMusic folder like the main DeeMusic app
        app_name = "DeeMusic"
        try:
            home_dir = Path.home()
            if sys.platform == "win32":
                # Windows: %APPDATA%\DeeMusic
                appdata = os.getenv('APPDATA')
                if appdata:
                    self.config_dir = Path(appdata) / app_name
                else:
                    # Fallback if APPDATA isn't set
                    self.config_dir = home_dir / app_name
            elif sys.platform == "darwin":
                # macOS: ~/Library/Application Support/DeeMusic
                self.config_dir = home_dir / "Library" / "Application Support" / app_name
            else:
                # Linux/Other: ~/.config/DeeMusic
                xdg_config_home = os.getenv('XDG_CONFIG_HOME')
                if xdg_config_home:
                    self.config_dir = Path(xdg_config_home) / app_name
                else:
                    self.config_dir = home_dir / ".config" / app_name
        except Exception as e:
            logger.error(f"Could not determine standard config directory: {e}. Falling back to relative path.")
            self.config_dir = Path('.') / 'user_config'
        
        # Use the main DeeMusic settings.json file instead of separate config.json
        self.config_file = self.config_dir / "settings.json"
        self.scan_results_file = self.config_dir / "scan_results.json"
        self.fast_comparison_results_file = self.config_dir / "fast_comparison_results.json"
        
        # Ensure config directory exists
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        # Default configuration
        self.defaults = {
            "library_paths": [],
            "deezer_arl": "",
            "deemusic_path": "",
            "supported_formats": [".mp3", ".aac", ".ogg", ".wma", ".opus", ".ra", ".mp2", ".flac", ".alac", ".ape", ".wv", ".tta", ".mlp", ".wav", ".aiff", ".pcm", ".bwf", ".m4a"],
            "album_match_threshold": 70,  # Lower threshold for album matching (more lenient)
            "track_match_threshold": 80,  # Higher threshold for track matching (more strict)
        }
        
        self.config = self.defaults.copy()
        self.load_config()
    
    def load_config(self) -> None:
        """Load configuration from main settings.json file."""
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    settings_data = json.load(f)
                
                # Extract library_scanner settings
                library_scanner = settings_data.get('library_scanner', {})
                
                # Map settings from the library_scanner section
                if 'library_paths' in library_scanner:
                    self.config['library_paths'] = library_scanner['library_paths']
                if 'album_match_threshold' in library_scanner:
                    self.config['album_match_threshold'] = library_scanner['album_match_threshold']
                if 'track_match_threshold' in library_scanner:
                    self.config['track_match_threshold'] = library_scanner['track_match_threshold']
                if 'supported_formats' in library_scanner:
                    self.config['supported_formats'] = library_scanner['supported_formats']
                if 'deemusic_path' in library_scanner:
                    self.config['deemusic_path'] = library_scanner['deemusic_path']
                
                # Get Deezer ARL from main deezer section
                deezer_config = settings_data.get('deezer', {})
                if 'arl' in deezer_config and deezer_config['arl']:
                    self.config['deezer_arl'] = deezer_config['arl']
                
                logger.info(f"Configuration loaded from {self.config_file} (library_scanner section)")
            else:
                logger.info("No settings.json file found, using defaults")
        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
            logger.info("Using default configuration")
    
    def save_config(self) -> None:
        """Save configuration to main settings.json file."""
        try:
            # Load existing settings
            settings_data = {}
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    settings_data = json.load(f)
            
            # Ensure library_scanner section exists
            if 'library_scanner' not in settings_data:
                settings_data['library_scanner'] = {}
            
            # Update library_scanner section with current config
            library_scanner = settings_data['library_scanner']
            library_scanner['library_paths'] = self.config.get('library_paths', [])
            library_scanner['album_match_threshold'] = self.config.get('album_match_threshold', 75)
            library_scanner['track_match_threshold'] = self.config.get('track_match_threshold', 80)
            library_scanner['supported_formats'] = self.config.get('supported_formats', [".mp3", ".aac", ".ogg", ".wma", ".opus", ".ra", ".mp2", ".flac", ".alac", ".ape", ".wv", ".tta", ".mlp", ".wav", ".aiff", ".pcm", ".bwf", ".m4a"])
            library_scanner['deemusic_path'] = self.config.get('deemusic_path', '')
            
            # Handle Deezer ARL - save to main deezer section
            if 'deezer_arl' in self.config and self.config['deezer_arl']:
                if 'deezer' not in settings_data:
                    settings_data['deezer'] = {}
                settings_data['deezer']['arl'] = self.config['deezer_arl']
            
            # Save updated settings
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(settings_data, f, indent=4, ensure_ascii=False)
            
            logger.info(f"Configuration saved to {self.config_file} (library_scanner section)")
        except Exception as e:
            logger.error(f"Error saving configuration: {e}")
    
    def save_scan_results(self, albums: List[Dict[str, Any]]) -> None:
        """Save scan results to file (album-level)."""
        try:
            scan_data = {
                "scan_timestamp": datetime.now().isoformat(),
                "library_paths": self.get_library_paths(),
                "album_count": len(albums),
                "albums": albums
            }
            with open(self.scan_results_file, 'w', encoding='utf-8') as f:
                json.dump(scan_data, f, indent=2, ensure_ascii=False)
            logger.info(f"Scan results saved to {self.scan_results_file} - {len(albums)} albums")
        except Exception as e:
            logger.error(f"Error saving scan results: {e}")

    def load_scan_results(self) -> Optional[Dict[str, Any]]:
        """Load scan results from file (album-level or track-level for backward compatibility)."""
        try:
            if self.scan_results_file.exists():
                with open(self.scan_results_file, 'r', encoding='utf-8') as f:
                    scan_data = json.load(f)
                
                # Handle different scan result formats and convert to album format
                if 'albums' in scan_data:
                    # Already in correct album format
                    scan_data['album_count'] = len(scan_data['albums'])
                    logger.info("Found scan results in album format")
                elif 'tracks' in scan_data:
                    # Convert tracks to albums format
                    scan_data['albums'] = scan_data['tracks']
                    scan_data['album_count'] = len(scan_data['tracks'])
                    logger.info("Converted tracks format to album format")
                elif 'files' in scan_data:
                    # Convert files to albums format (this handles the corrupted data)
                    logger.info("Found scan results in files format, converting to albums...")
                    albums = self._convert_files_to_albums(scan_data['files'])
                    scan_data['albums'] = albums
                    scan_data['album_count'] = len(albums)
                    # Add missing required fields
                    if 'library_paths' not in scan_data:
                        scan_data['library_paths'] = self.get_library_paths()
                    # Save the corrected format immediately
                    self.save_scan_results(albums)
                    logger.info(f"Converted and saved {len(albums)} albums from files format")
                else:
                    logger.warning("Scan results file missing 'albums', 'tracks', or 'files' key")
                    return None
                
                # Validate the scan data (with more lenient validation)
                if self._is_scan_data_valid_lenient(scan_data):
                    logger.info(f"Scan results loaded from {self.scan_results_file} - {scan_data.get('album_count', 0)} albums")
                    return scan_data
                else:
                    logger.warning("Scan results file is invalid or outdated")
                    return None
            else:
                logger.info("No scan results file found")
                return None
        except Exception as e:
            logger.error(f"Error loading scan results: {e}")
            return None
    def _convert_files_to_albums(self, files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert file-based scan results to album-based format."""
        albums_dict = {}
        
        for file_info in files:
            if not isinstance(file_info, dict):
                continue
                
            album_artist = file_info.get('album_artist', '').strip()
            album_name = file_info.get('album', '').strip()
            
            # Skip invalid entries (this filters out the "G:\" entries)
            if not album_artist or not album_name or album_artist.lower() == 'various artists':
                continue
            if album_artist.endswith(':\\') or ':\\' in album_artist:
                continue  # Skip entries where artist is a drive path
                
            # Create album key
            album_key = f"{album_artist}|{album_name}"
            
            if album_key not in albums_dict:
                # Extract folder path from file path
                file_path = file_info.get('path', '')
                folder_path = str(Path(file_path).parent) if file_path else file_path
                
                albums_dict[album_key] = {
                    'album_artist': album_artist,
                    'album': album_name,
                    'folder_path': folder_path,
                    'year': file_info.get('year', 0) or 0,
                    'genre': file_info.get('genre', ''),
                    'num_tracks': 0,
                    'total_duration': 0,
                    'file_formats': set()
                }
            
            # Update album info
            album_info = albums_dict[album_key]
            album_info['num_tracks'] += 1
            
            # Add file format if available
            file_format = file_info.get('format', 'mp3')
            if file_format:
                album_info['file_formats'].add(file_format)
        
        # Convert sets to lists for JSON serialization
        albums = []
        for album_info in albums_dict.values():
            album_info['file_formats'] = list(album_info['file_formats'])
            albums.append(album_info)
        
        return albums

    def _is_scan_data_valid_lenient(self, scan_data: Dict[str, Any]) -> bool:
        """Check if scan data is valid with more lenient validation."""
        if not isinstance(scan_data, dict):
            return False
        
        # Must have albums data
        if 'albums' not in scan_data or not scan_data['albums']:
            logger.warning("Scan data missing 'albums' or albums is empty")
            return False
        
        # Check if scan is not too old (optional, more lenient)
        if 'scan_timestamp' in scan_data:
            try:
                scan_timestamp = datetime.fromisoformat(scan_data['scan_timestamp'])
                days_old = (datetime.now() - scan_timestamp).days
                if days_old > 90:  # More lenient - 90 days instead of 30
                    logger.info(f"Scan results are {days_old} days old, but still accepting")
            except (ValueError, TypeError):
                logger.warning("Invalid scan timestamp format, but continuing")
        
        return True

    def _is_scan_data_valid(self, scan_data: Dict[str, Any]) -> bool:
        """Check if scan data is valid and current (album-level or track-level)."""
        if not isinstance(scan_data, dict):
            return False
        # Accept either albums or tracks
        required_fields = ['scan_timestamp', 'library_paths']
        for field in required_fields:
            if field not in scan_data:
                logger.warning(f"Missing required field in scan data: {field}")
                return False
        if 'albums' not in scan_data and 'tracks' not in scan_data:
            logger.warning("Scan data missing both 'albums' and 'tracks'")
            return False
        # Check if library paths have changed
        current_paths = set(self.get_library_paths())
        saved_paths = set(scan_data.get('library_paths', []))
        if current_paths != saved_paths:
            logger.info("Library paths have changed, scan results may be outdated")
            return False
        # Check if scan is not too old (optional)
        try:
            scan_timestamp = datetime.fromisoformat(scan_data['scan_timestamp'])
            days_old = (datetime.now() - scan_timestamp).days
            if days_old > 30:
                logger.info(f"Scan results are {days_old} days old, may be outdated")
                return False
        except (ValueError, TypeError):
            logger.warning("Invalid scan timestamp format")
            return False
        return True
    
    def clear_scan_results(self) -> None:
        """Clear saved scan results."""
        try:
            if self.scan_results_file.exists():
                self.scan_results_file.unlink()
                logger.info("Scan results cleared")
        except Exception as e:
            logger.error(f"Error clearing scan results: {e}")
    
    def get_scan_results_info(self) -> Optional[Dict[str, Any]]:
        """Get information about saved scan results without loading all tracks."""
        try:
            if self.scan_results_file.exists():
                with open(self.scan_results_file, 'r', encoding='utf-8') as f:
                    scan_data = json.load(f)
                
                return {
                    "scan_timestamp": scan_data.get('scan_timestamp'),
                    "track_count": scan_data.get('track_count', 0),
                    "library_paths": scan_data.get('library_paths', []),
                    "file_size": self.scan_results_file.stat().st_size,
                    "is_valid": self._is_scan_data_valid(scan_data)
                }
            else:
                return None
        except Exception as e:
            logger.error(f"Error getting scan results info: {e}")
            return None
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value."""
        keys = key.split('.')
        value = self.config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def set(self, key: str, value: Any) -> None:
        """Set configuration value."""
        keys = key.split('.')
        config_ref = self.config
        
        for k in keys[:-1]:
            if k not in config_ref:
                config_ref[k] = {}
            config_ref = config_ref[k]
        
        config_ref[keys[-1]] = value
        self.save_config()
    
    def add_library_path(self, path: str) -> None:
        """Add a library path to scan."""
        library_paths = self.get("library_paths", [])
        if path not in library_paths:
            library_paths.append(path)
            self.set("library_paths", library_paths)
            
            # Clear scan results when library paths change
            self.clear_scan_results()
    
    def remove_library_path(self, path: str) -> None:
        """Remove a library path from scanning."""
        library_paths = self.get("library_paths", [])
        if path in library_paths:
            library_paths.remove(path)
            self.set("library_paths", library_paths)
            
            # Clear scan results when library paths change
            self.clear_scan_results()
    
    def get_library_paths(self) -> list:
        """Get all configured library paths."""
        return self.get("library_paths", [])
    
    def set_deezer_arl(self, arl: str) -> None:
        """Set Deezer ARL token."""
        self.set("deezer_arl", arl)
    
    def get_deezer_arl(self) -> str:
        """Get Deezer ARL token."""
        return self.get("deezer_arl", "")
    
    def set_deemusic_path(self, path: str) -> None:
        """Set path to DeeMusic executable."""
        self.set("deemusic_path", path)
    
    def get_deemusic_path(self) -> str:
        """Get path to DeeMusic executable."""
        return self.get("deemusic_path", "")
    
    def get_supported_formats(self) -> list:
        """Get list of supported audio formats."""
        return self.get("supported_formats", [".mp3", ".aac", ".ogg", ".wma", ".opus", ".ra", ".mp2", ".flac", ".alac", ".ape", ".wv", ".tta", ".mlp", ".wav", ".aiff", ".pcm", ".bwf", ".m4a"])
    
    def is_supported_format(self, file_path: str) -> bool:
        """Check if file format is supported."""
        file_ext = Path(file_path).suffix.lower()
        return file_ext in self.get_supported_formats() 

    def save_fast_comparison_results(self, results: Dict[str, Any], library_hash: str) -> None:
        """Save fast album comparison results to file."""
        try:
            comparison_data = {
                "timestamp": datetime.now().isoformat(),
                "library_hash": library_hash,
                "results": results
            }
            
            with open(self.fast_comparison_results_file, 'w', encoding='utf-8') as f:
                json.dump(comparison_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Fast comparison results saved to {self.fast_comparison_results_file}")
        except Exception as e:
            logger.error(f"Error saving fast comparison results: {e}")
    
    def load_fast_comparison_results(self, library_hash: str) -> Optional[Dict[str, Any]]:
        """Load fast album comparison results from file if library hash matches."""
        try:
            if self.fast_comparison_results_file.exists():
                with open(self.fast_comparison_results_file, 'r', encoding='utf-8') as f:
                    comparison_data = json.load(f)
                
                # Check if library hash matches
                if comparison_data.get('library_hash') == library_hash:
                    logger.info(f"Fast comparison results loaded from {self.fast_comparison_results_file}")
                    return comparison_data.get('results')
                else:
                    logger.info("Library hash changed, fast comparison results are outdated")
                    return None
            else:
                logger.info("No fast comparison results file found")
                return None
        except Exception as e:
            logger.error(f"Error loading fast comparison results: {e}")
            return None
    
    def get_fast_comparison_results_info(self) -> Optional[Dict[str, Any]]:
        """Get information about saved fast comparison results without loading all data."""
        try:
            if self.fast_comparison_results_file.exists():
                with open(self.fast_comparison_results_file, 'r', encoding='utf-8') as f:
                    comparison_data = json.load(f)
                
                return {
                    "timestamp": comparison_data.get('timestamp'),
                    "library_hash": comparison_data.get('library_hash'),
                    "file_size": self.fast_comparison_results_file.stat().st_size,
                    "has_results": 'results' in comparison_data
                }
            else:
                return None
        except Exception as e:
            logger.error(f"Error getting fast comparison results info: {e}")
            return None
    
    def clear_fast_comparison_results(self) -> None:
        """Clear saved fast comparison results."""
        try:
            if self.fast_comparison_results_file.exists():
                self.fast_comparison_results_file.unlink()
                logger.info("Fast comparison results cleared")
        except Exception as e:
            logger.error(f"Error clearing fast comparison results: {e}")
    
    def get_album_match_threshold(self) -> int:
        """Get album matching threshold (more lenient for album titles)."""
        return self.config.get("album_match_threshold", 70)
    
    def get_track_match_threshold(self) -> int:
        """Get track matching threshold (more strict for track titles)."""
        return self.config.get("track_match_threshold", 80)
    
    def set_album_match_threshold(self, threshold: int) -> None:
        """Set album matching threshold."""
        self.config["album_match_threshold"] = max(0, min(100, threshold))
        self.save_config()
    
    def set_track_match_threshold(self, threshold: int) -> None:
        """Set track matching threshold."""
        self.config["track_match_threshold"] = max(0, min(100, threshold))
        self.save_config() 