"""Configuration manager for DeeMusic."""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional
import os
import sys # Import sys for platform check

logger = logging.getLogger(__name__)

class ConfigManager:
    """Manages application configuration settings."""
    
    def __init__(self, config_dir: Optional[Path] = None):
        """Initialize the ConfigManager.
        
        Args:
            config_dir: Optional directory for configuration files
        """
        logger.info(f"Initializing ConfigManager with config_dir argument: {config_dir}")
        
        if config_dir is None:
            # Determine platform-specific default location
            app_name = "DeeMusic" 
            try:
                home_dir = Path.home() # Standard way to get home directory
                if sys.platform == "win32":
                    # Windows: %APPDATA%\DeeMusic
                    appdata = os.getenv('APPDATA')
                    if appdata:
                        default_dir = Path(appdata) / app_name
                    else:
                        # Fallback if APPDATA isn't set (unusual)
                        default_dir = home_dir / app_name 
                elif sys.platform == "darwin":
                    # macOS: ~/Library/Application Support/DeeMusic
                    default_dir = home_dir / "Library" / "Application Support" / app_name
                else:
                    # Linux/Other: ~/.config/DeeMusic (or ~/.local/share/DeeMusic)
                    # Using .config is common
                    xdg_config_home = os.getenv('XDG_CONFIG_HOME')
                    if xdg_config_home:
                        default_dir = Path(xdg_config_home) / app_name
                    else:
                        default_dir = home_dir / ".config" / app_name
            except Exception as e:
                 logger.error(f"Could not determine standard config directory: {e}. Falling back to relative path.")
                 # Fallback if home directory or standard paths cannot be determined
                 default_dir = Path('.') / 'user_config' # Use a different name to avoid conflict with 'test_config'

            config_dir = default_dir
            
        logger.info(f"Using config directory: {config_dir}") # Changed level to INFO
            
        self.config_dir = config_dir.resolve() # Resolve to absolute path
        # Always use settings.json as the primary config file
        self.config_file = self.config_dir / 'settings.json'
        self.legacy_config_file = self.config_dir / 'config.json'
        logger.info(f"Config file path: {self.config_file}")
        
        # Ensure config directory exists
        self._ensure_config_dir()
        
        # Load settings
        self.config: Dict[str, Any] = {}
        self.load_config()
        
    def _ensure_config_dir(self):
        """Create the configuration directory if it doesn't exist."""
        if not self.config_dir.exists():
            logger.debug(f"Creating config directory: {self.config_dir}")
            self.config_dir.mkdir(parents=True, exist_ok=True)
        
    def load_config(self) -> Dict[str, Any]:
        """Load configuration from file or initialize with defaults."""
        logger.info(f"Loading settings from {self.config_file}")
        
        default_config = {
            'deezer': {
                'arl': None
            },
            'downloads': {
                'path': 'downloads',
                'concurrent_downloads': 5,  # Restored original value for better performance
                'quality': 'MP3_320',
                'saveArtwork': True,
                'embedArtwork': True,
                'embeddedArtworkSize': 1200,
                'artistArtworkSize': 1200,
                'albumArtworkSize': 1200,
                'artistImageTemplate': 'folder',
                'albumImageTemplate': 'cover',
                'artistImageFormat': 'jpg',
                'albumImageFormat': 'jpg',
                'overwrite_existing': False,
                'skip_existing': True,
                'create_playlist_m3u': False,
                'filename_templates': {
                    'track': '{artist} - {title}',
                    'album_track': '{track_number:02d}. {title}',
                    'playlist_track': '{playlist_name}/{artist} - {title}'
                },
                'folder_structure': {
                    'create_playlist_folders': True,
                    'create_artist_folders': True,
                    'create_album_folders': True,
                    'create_cd_folders': True,
                    'create_playlist_structure': False,
                    'create_singles_structure': True,
                    'templates': {
                        'playlist': '%playlist%',
                        'artist': '%artist%',
                        'album': '%album%',
                        'cd': 'CD %disc_number%'
                    }
                },
                'character_replacement': {
                    'enabled': True,
                    'replacement_char': '_',
                    'custom_replacements': {
                        '<': '_',
                        '>': '_',
                        ':': '_',
                        '"': '_',
                        '/': '_',
                        '\\': '_',
                        '|': '_',
                        '?': '_',
                        '*': '_'
                    }
                }
            },
            'appearance': {
                'theme': 'light',
                'font_size': 11
            },
            'network': {
                'proxy': {
                    'enabled': False,
                    'type': 'http',  # 'http', 'https', 'socks4', 'socks5'
                    'host': '',
                    'port': '',
                    'username': '',
                    'password': '',
                    'use_for_downloads': True,
                    'use_for_api': True
                },
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36',
                'timeout': 30,
                'retries': 3
            },
            'lyrics': {
                'enabled': True,  # Master switch to disable all lyrics processing if needed
                'lrc_enabled': True,
                'txt_enabled': False,
                'embed_sync_lyrics': True,
                'embed_plain_lyrics': False,
                'language': 'Original',
                'location': 'With Audio Files',
                'custom_path': '',
                'sync_offset': 0,
                'encoding': 'UTF-8'
            },
            'performance': {
                'lazy_loading': True,
                'image_preloading': True,
                'memory_cache_size_mb': 30,
                'disk_cache_size_mb': 100,
                'max_concurrent_image_loads': 5,
                'viewport_check_interval_ms': 200,
                'preload_batch_size': 5
            }
        }
        
        try:
            loaded_config = {}
            
            # First check if settings.json exists
            if self.config_file.exists():
                logger.debug(f"Found settings file at {self.config_file}")
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    settings_config = json.load(f)
                    loaded_config = settings_config
            # Then check if legacy config.json exists
            elif self.legacy_config_file.exists():
                logger.debug(f"Found legacy config file at {self.legacy_config_file}")
                with open(self.legacy_config_file, 'r', encoding='utf-8') as f:
                    legacy_config = json.load(f)
                    loaded_config = legacy_config
                    
            if loaded_config:
                # Merge with defaults (to ensure all keys exist)
                logger.debug("Merging settings with defaults")
                merged_config = self._merge_configs(default_config, loaded_config)
                logger.debug(f"Merged result: {merged_config}")
                self.config = merged_config
                # MOVED LOGGING FOR FILENAME TEMPLATES AFTER self.config is set
                filename_templates_after_merge = self.config.get('downloads', {}).get('filename_templates')
                logger.info(f"ConfigManager.load_config: filename_templates in self.config AFTER MERGE: {filename_templates_after_merge}")
            else:
                logger.debug("No existing config found, using defaults")
                self.config = default_config
                # Save default config
                self.save_config()
                
            logger.debug(f"Loaded settings: {self.config}")
            return self.config
                
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON in config file: {self.config_file}")
            self.config = default_config
            return default_config
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            self.config = default_config
            return default_config
            
    def _merge_configs(self, default_config_part: Dict, loaded_config_part: Dict) -> Dict:
        """
        Recursively merge loaded_config_part into default_config_part.
        Ensures that if a default key expects a dictionary, a non-dictionary
        value from loaded_config_part does not overwrite the dictionary structure.
        Values from loaded_config_part take precedence if types are compatible or
        if the key is new.
        """
        merged = default_config_part.copy()

        for key, loaded_value in loaded_config_part.items():
            if key not in merged: # New key from loaded config, add it
                merged[key] = loaded_value
            else: # Key exists in both default and loaded
                default_value = merged[key] # Value from the default structure

                if isinstance(default_value, dict) and isinstance(loaded_value, dict):
                    # Both are dicts, recurse to merge them
                    merged[key] = self._merge_configs(default_value, loaded_value)
                elif isinstance(default_value, dict) and not isinstance(loaded_value, dict):
                    # Default is a dict, but loaded value is not (e.g., null, string).
                    # This indicates potential corruption or an outdated config.
                    # Keep the default dictionary structure to prevent errors.
                    logger.warning(
                        f"Config Merge: Default for '{key}' is a dictionary, "
                        f"but loaded config has a non-dictionary value (type: {type(loaded_value).__name__}). "
                        f"Keeping default dictionary structure for '{key}'."
                    )
                    # merged[key] already holds default_value from default_config_part.copy(), so no change needed here.
                else:
                    # Default is not a dict, OR
                    # Default is not a dict AND loaded is not a dict (e.g. both are strings, numbers) OR
                    # Default is a dict AND loaded is also a dict (handled by the first 'if') - this 'else' implies default is not dict.
                    # In these cases, the loaded value takes precedence.
                    merged[key] = loaded_value
        return merged
            
    def save_config(self):
        """Save current configuration to file."""
        logger.info(f"ConfigManager.save_config: Attempting to save. Current self.config keys: {list(self.config.keys())}")
        
        # ADDED LOGGING FOR FILENAME TEMPLATES BEFORE SAVE - Placed at the very start of the method
        filename_templates_at_save_start = self.config.get('downloads', {}).get('filename_templates')
        logger.info(f"ConfigManager.save_config: filename_templates in self.config AT START of save_config: {filename_templates_at_save_start}")

        try:
            # Ensure config dir exists
            self._ensure_config_dir()
            
            # Write config to file
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4)
                
            logger.debug(f"Saved settings to {self.config_file}")
            
            # Remove legacy config file if it exists to avoid confusion
            if self.legacy_config_file.exists():
                try:
                    os.remove(self.legacy_config_file)
                    logger.debug(f"Removed legacy config file: {self.legacy_config_file}")
                except Exception as e:
                    logger.warning(f"Failed to remove legacy config file: {e}")
                
            return True
        except Exception as e:
            logger.error(f"Error saving config: {e}")
            return False
            
    def get_setting(self, path: str, default: Any = None) -> Any:
        """Get a setting value using dot notation path.
        
        Args:
            path: Setting path (e.g. 'downloads.path')
            default: Default value if setting not found
            
        Returns:
            Setting value or default
        """
        try:
            value = self._get_nested_value(self.config, path.split('.'))
            logger.debug(f"Got setting {path}: {value}")
            return value
        except (KeyError, TypeError):
            logger.debug(f"Setting {path} not found, using default: {default}")
            return default
            
    def _get_nested_value(self, config: Dict, keys: list) -> Any:
        """Get a nested value from the config dictionary."""
        if not keys:
            return config
            
        key = keys[0]
        if len(keys) == 1:
            return config[key]
            
        return self._get_nested_value(config[key], keys[1:])
            
    def set_setting(self, path: str, value: Any):
        """Set a setting value using dot notation path.
        
        Args:
            path: Setting path (e.g. 'downloads.path')
            value: Value to set
        """
        keys = path.split('.')
        
        # SAFETY: Cap concurrent downloads at 5 for system stability
        if path == 'downloads.concurrent_downloads' and isinstance(value, (int, float)):
            if value > 5:
                logger.warning(f"Capping concurrent downloads from {value} to 5 for system stability")
                value = 5
        
        logger.info(f"Setting {path} = {value}")
        
        # Update the config
        self._set_nested_value(self.config, keys, value)
        
        # Save the updated config
        self.save_config()
        
    def _set_nested_value(self, config: Dict, keys: list, value: Any):
        """Set a nested value in the config dictionary, creating parent dicts if necessary."""
        if not keys:
            logger.warning("ConfigManager._set_nested_value called with empty keys.")
            return

        current_level = config
        for i, key in enumerate(keys[:-1]): # Iterate through keys except the last one
            if key not in current_level or not isinstance(current_level[key], dict):
                logger.debug(f"ConfigManager._set_nested_value: Creating missing dict for key '{key}' at depth {i}")
                current_level[key] = {} # Create a new dict if key is missing or not a dict
            current_level = current_level[key]
        
        # Set the value at the final key
        final_key = keys[-1]
        current_level[final_key] = value
        logger.debug(f"ConfigManager._set_nested_value: Set '{'.'.join(keys)}' to {value}") 