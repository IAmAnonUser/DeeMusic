"""
Theme manager for DeeMusic.
Handles application themes and styles.
"""

from PyQt6.QtCore import QObject, pyqtSignal
import json
import os
from pathlib import Path
from PyQt6.QtWidgets import QApplication, QWidget, QMainWindow

class ThemeManager(QObject):
    """Manages application themes."""
    
    theme_changed = pyqtSignal(str)  # Signal emitted when theme changes
    
    LIGHT_THEME = {
        "name": "light",
        "background": "#FFFFFF",        # Content area background
        "surface": "#F5F2F8",          # Sidebar, cards, other elevated surfaces (Deezer-like off-white/light lavender)
        "primary": "#A238FF",          # Deezer's primary purple
        "primary_variant": "#8A2EE5",   # Slightly darker purple for interactions
        "secondary": "#EF5466",        # Secondary accent (e.g., for play buttons or highlights) - Deezer uses various, this is a guess
        "text": "#000000",              # Primary text on light backgrounds
        "text_secondary": "#555555",    # Subtitles, less important text (dark gray)
        "text_on_primary": "#FFFFFF",   # Text on primary color backgrounds (e.g., buttons)
        "text_on_surface": "#000000",   # Text on surface color backgrounds
        "divider": "#EAEAEA",           # Dividers
        "hover_bg": "#EAE0F4",          # Hover background for sidebar items (light purple tint)
        "active_bg": "#D5C0E8",         # Background for active/selected sidebar items
        "icon_color": "#333333",
        "icon_active_color": "#A238FF", # Purple for active icon
        "scrollbar_bg": "#F0F0F0",
        "scrollbar_handle": "#C0C0C0",
        "scrollbar_handle_hover": "#A0A0A0",
        "search_bar_bg": "#ECECEC",
        "button_secondary_bg": "#E0E0E0",
        "button_secondary_text": "#000000",
        "button_secondary_hover_bg": "#D0D0D0",
        "player_bg": "#F9F9F9",
        "header_background": "#FFFFFF", # Specific for header, or fallback to surface
        "sidebar_background": "#FFFFFF", # Match Deezer's light sidebar
        "content_background": "#F5F2F8",
    }
    
    DARK_THEME = {
        "name": "dark",
        "background": "#121212",        # Dark background for content area
        "surface": "#1C1C24",          # Darker sidebar, cards (Deezer-like dark gray/blue)
        "primary": "#A238FF",          # Deezer's primary purple (can remain same or be adjusted)
        "primary_variant": "#B86EFF",   # Slightly lighter purple for interactions on dark theme
        "secondary": "#EF5466",        # Secondary accent
        "text": "#FFFFFF",              # Primary text on dark backgrounds
        "text_secondary": "#AAAAAA",    # Subtitles, less important text (light gray)
        "text_on_primary": "#FFFFFF",   # Text on primary color backgrounds
        "text_on_surface": "#FFFFFF",   # Text on surface color backgrounds
        "divider": "#333333",           # Dividers
        "hover_bg": "#2A2A33",          # Hover background for sidebar items (darker shade)
        "active_bg": "#3A2D4F",         # Background for active/selected sidebar items (dark purple tint)
        "icon_color": "#CCCCCC",
        "icon_active_color": "#A238FF", # Purple for active icon
        "scrollbar_bg": "#2C2C2C",
        "scrollbar_handle": "#555555",
        "scrollbar_handle_hover": "#777777",
        "search_bar_bg": "#2E2E2E",
        "button_secondary_bg": "#3C3C3C",
        "button_secondary_text": "#FFFFFF",
        "button_secondary_hover_bg": "#4C4C4C",
        "player_bg": "#181818",
        "header_background": "#1C1C1C", # Darker header
        "sidebar_background": "#1C1C1C", # Darker sidebar
        "content_background": "#121212",
    }
    
    def __init__(self):
        """Initialize theme manager."""
        super().__init__()
        self.current_theme = "dark"
        self.load_theme_preference()
        # self.app = QApplication.instance() # Get QApplication instance if needed for apply_theme
        
    def apply_theme(self, theme_name: str, main_window: QWidget = None):
        """Apply the specified theme to the application."""
        from PyQt6.QtWidgets import QApplication # Local import if issues arise, though global seems to be what model did.
        print(f"[ThemeManager] ACTION apply_theme: Called with theme_name='{theme_name}'. main_window: {main_window} (type: {type(main_window)})") # DEBUG

        if theme_name not in ["light", "dark"]:
            print(f"[ThemeManager] WARNING apply_theme: Invalid theme_name '{theme_name}'. Defaulting to 'dark'.") # DEBUG
            theme_name = "dark"
            
        self.current_theme = theme_name # Ensure self.current_theme is updated with the validated theme_name
        print(f"[ThemeManager] INFO apply_theme: current_theme set to '{self.current_theme}'.") # DEBUG
        
        stylesheet = self.get_stylesheet(theme_name)
        # Simple hash to avoid logging giant stylesheet string
        import hashlib
        stylesheet_hash = hashlib.md5(stylesheet.encode('utf-8')).hexdigest()
        print(f"[ThemeManager] INFO apply_theme: Generated stylesheet (MD5: {stylesheet_hash}).") # DEBUG
        
        app = QApplication.instance()
        if app:
            print(f"[ThemeManager] INFO apply_theme: QApplication instance found: {app}.") # DEBUG
            
            if main_window:
                print(f"[ThemeManager] INFO apply_theme: main_window provided. Type: {type(main_window)}, ObjectName: {main_window.objectName() if hasattr(main_window, 'objectName') else 'N/A'}.") # DEBUG
                
                current_style = main_window.style()
                if current_style:
                    print("[ThemeManager] ACTION apply_theme: Calling main_window.style().unpolish().") # DEBUG
                    current_style.unpolish(main_window)
                else:
                    print("[ThemeManager] WARNING apply_theme: main_window.style() is None. Skipping unpolish.") # DEBUG

                print("[ThemeManager] ACTION apply_theme: Calling app.setStyleSheet().") # DEBUG
                app.setStyleSheet(stylesheet) # Apply to the whole app
                print("[ThemeManager] INFO apply_theme: app.setStyleSheet() called.") # DEBUG
                
                if current_style:
                    print("[ThemeManager] ACTION apply_theme: Calling main_window.style().polish().") # DEBUG
                    current_style.polish(main_window)
                else:
                    print("[ThemeManager] WARNING apply_theme: main_window.style() is None. Skipping polish.") # DEBUG

                print("[ThemeManager] ACTION apply_theme: Calling main_window.update().") # DEBUG
                main_window.update()
                print("[ThemeManager] INFO apply_theme: main_window.update() called.") # DEBUG
            else:
                print("[ThemeManager] WARNING apply_theme: main_window not provided. Applying stylesheet directly to app.") # DEBUG
                app.setStyleSheet(stylesheet)
            
            print(f"[ThemeManager] SUCCESS apply_theme: Stylesheet applied for theme '{self.current_theme}'.") # DEBUG
        else:
            print("[ThemeManager] ERROR apply_theme: QApplication instance NOT found!") # DEBUG
        
    def load_theme_preference(self):
        """Load saved theme preference and apply it."""
        # Default to dark if no config exists or is invalid
        loaded_theme = "dark" 
        config_path = Path.home() / ".deemusic" / "config.json"
        if config_path.exists():
            try:
                with open(config_path, "r") as f:
                    config = json.load(f)
                    loaded_theme = config.get("theme", "dark")
            except Exception:
                # logger.error(f"Error loading theme from config: {e}. Defaulting to dark.")
                loaded_theme = "dark"
        
        print(f"[ThemeManager] INFO load_theme_preference: Loaded theme '{loaded_theme}' from preference.") # DEBUG
        self.current_theme = loaded_theme 
        print(f"[ThemeManager] INFO load_theme_preference: current_theme set to '{self.current_theme}'.") # DEBUG
        # self.apply_theme(self.current_theme) # apply_theme is called by MainWindow after this, or on toggle
        # No, it's better if ThemeManager ensures the loaded theme is active immediately after loading.
        print(f"[ThemeManager] Loaded theme preference: {self.current_theme}. Applying it now.") # DEBUG
        # self.apply_theme(self.current_theme) # Apply the loaded theme # REMOVED

        # REMOVE THE TOGGLING LOGIC FROM HERE:
        # self.current_theme = "light" if self.current_theme == "dark" else "dark"
        # self.save_theme_preference()
        # self.apply_theme(self.current_theme)
        
    def save_theme_preference(self):
        """Save current theme preference."""
        config_path = Path.home() / ".deemusic" / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        config = {"theme": self.current_theme}
        try:
            with open(config_path, "w") as f:
                json.dump(config, f)
            print(f"[ThemeManager] INFO save_theme_preference: Saved theme '{self.current_theme}' to {config_path}.") # DEBUG
        except Exception as e: # Catch specific exception if possible
            print(f"[ThemeManager] ERROR save_theme_preference: Failed to save theme. Error: {e}") # DEBUG
            
    def get_theme(self):
        """Get current theme colors."""
        return self.DARK_THEME if self.current_theme == "dark" else self.LIGHT_THEME

    def toggle_theme(self):
        """Toggle between light and dark themes."""
        print(f"[ThemeManager] ACTION toggle_theme: Called. Current theme before toggle: '{self.current_theme}'.") # DEBUG
        
        old_theme = self.current_theme
        self.current_theme = "light" if self.current_theme == "dark" else "dark"
        print(f"[ThemeManager] INFO toggle_theme: Theme toggled from '{old_theme}' to '{self.current_theme}'.") # DEBUG
        
        print("[ThemeManager] ACTION toggle_theme: Calling save_theme_preference().") # DEBUG
        self.save_theme_preference()
        
        print(f"[ThemeManager] ACTION toggle_theme: Emitting theme_changed signal with new theme '{self.current_theme}'.") # DEBUG
        self.theme_changed.emit(self.current_theme)
        print("[ThemeManager] INFO toggle_theme: theme_changed signal emitted.") # DEBUG
        
    def get_stylesheet(self, theme_name: str) -> str:
        # --- MODIFIED TO LOAD main.qss --- 
        # Construct the path to main.qss relative to this file (theme_manager.py)
        # Assuming theme_manager.py is in src/ui/ and main.qss is in src/ui/styles/
        current_dir = Path(__file__).resolve().parent
        main_qss_path = current_dir / "styles" / "main.qss"
        
        try:
            with open(main_qss_path, "r", encoding='utf-8') as f:
                stylesheet_content = f.read()
                print(f"[ThemeManager] Successfully loaded stylesheet from {main_qss_path}") # DEBUG
                return stylesheet_content
        except FileNotFoundError:
            print(f"[ThemeManager] ERROR: main.qss not found at {main_qss_path}") # DEBUG
            return "QWidget { background-color: red; }" # Fallback: make everything red if file not found
        except Exception as e:
            print(f"[ThemeManager] ERROR: Failed to read main.qss: {e}") # DEBUG
            return "QWidget { background-color: orange; }" # Fallback: make everything orange on other errors

# Add a main function to test the theme manager directly
if __name__ == "__main__":
    import sys
    from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QPushButton, QLabel
    
    print("Testing ThemeManager...")
    
    # Create a simple test app
    app = QApplication(sys.argv)
    
    class TestWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("Theme Test")
            self.resize(500, 400)
            
            # Central widget setup
            central = QWidget()
            self.setCentralWidget(central)
            layout = QVBoxLayout(central)
            
            # Add some test widgets
            label = QLabel("Test Label - Should change with theme")
            layout.addWidget(label)
            
            button = QPushButton("Test Button")
            layout.addWidget(button)
            
            # Add theme toggle button
            toggle_btn = QPushButton("Toggle Theme")
            layout.addWidget(toggle_btn)
            
            # Create and apply theme manager
            self.theme_manager = ThemeManager()
            
            # Connect toggle button
            toggle_btn.clicked.connect(self.theme_manager.toggle_theme)
    
    # Create and show window
    window = TestWindow()
    window.show()
    
    # Force the default theme application
    # window.theme_manager.apply_theme(window.theme_manager.current_theme)
    # In a real app, MainWindow would call this with itself as arg:
    window.theme_manager.apply_theme(window.theme_manager.current_theme, window)
    
    # Start event loop
    sys.exit(app.exec()) 