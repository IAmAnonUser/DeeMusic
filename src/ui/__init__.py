"""
DeeMusic UI package initialization.
"""

from .main_window import MainWindow
from .theme_manager import ThemeManager
from .folder_settings_dialog import FolderSettingsDialog

__all__ = ['MainWindow', 'ThemeManager', 'FolderSettingsDialog']

# This file makes the 'ui' directory a Python package. 