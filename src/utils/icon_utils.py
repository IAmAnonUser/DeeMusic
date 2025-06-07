import os
from PyQt6.QtGui import QIcon
import logging

logger = logging.getLogger(__name__)

# Base directory for assets, assuming it's relative to the 'ui' directory.
# This might need adjustment based on your actual project structure.
# If icon_utils.py is in src/utils/ and assets are in src/ui/assets/
# then the path needs to be constructed carefully.

# Let's assume icons are stored in a folder like src/ui/assets/icons/
# For now, let's make it relative to the ui directory's assets folder.
# The typical structure seen is assets within the ui folder itself.
UI_ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'ui', 'assets')

def get_icon(icon_name: str) -> QIcon | None:
    """
    Loads a QIcon from the assets/icons directory.

    Args:
        icon_name (str): The filename of the icon (e.g., "download.png").

    Returns:
        QIcon | None: The loaded QIcon, or None if not found or an error occurs.
    """
    # Construct a path assuming icon_utils.py is in src/utils 
    # and icons are in src/ui/assets/
    # Path from src/utils/icon_utils.py to src/ui/assets/
    # .. (to src) / ui / assets / icon_name
    
    # Simplified path for now: Assumes an 'icons' subfolder within UI_ASSETS_DIR
    # If your icons (like 'download.png') are directly in 'assets', adjust this.
    # The previous AlbumDetailPage usage suggests 'download.png' might be directly in 'assets' folder
    # next to 'back button.png'. Let's try that path construction.
    
    # Path from src/utils/icon_utils.py to src/ui/assets/icon_name
    icon_path = os.path.join(UI_ASSETS_DIR, icon_name)
    
    if os.path.exists(icon_path):
        try:
            icon = QIcon(icon_path)
            if not icon.isNull():
                logger.debug(f"Successfully loaded icon: {icon_path}")
                return icon
            else:
                logger.warning(f"Icon file found at {icon_path}, but QIcon isNull. File might be corrupted or not a valid image format.")
                return None
        except Exception as e:
            logger.error(f"Error loading icon {icon_path}: {e}", exc_info=True)
            return None
    else:
        logger.warning(f"Icon file not found at expected path: {icon_path}. UI_ASSETS_DIR was: {UI_ASSETS_DIR}")
        # Attempt a fallback: what if assets folder is next to utils? (src/assets)
        # This is less likely given typical structure.
        # FallbackPath: os.path.join(os.path.dirname(UI_ASSETS_DIR), '..', 'assets', icon_name)
        # For now, we stick to the most likely path used by other parts of the UI.
        return None

if __name__ == '__main__':
    # This is a simple test. For it to run, you'd need a QApplication instance.
    # And the pathing needs to be correct relative to where you run this test.
    
    # Example of how UI_ASSETS_DIR is resolved when this script is in src/utils:
    # __file__ -> C:/.../deemusic/src/utils/icon_utils.py
    # os.path.dirname(__file__) -> C:/.../deemusic/src/utils
    # os.path.join(..., '..') -> C:/.../deemusic/src
    # os.path.join(..., 'ui') -> C:/.../deemusic/src/ui
    # os.path.join(..., 'assets') -> C:/.../deemusic/src/ui/assets
    print(f"Calculated UI_ASSETS_DIR: {UI_ASSETS_DIR}")
    
    # To test, you would need to run this from the project root or ensure PyQt6 is available
    # and a 'download.png' exists at the expected location.
    # from PyQt6.QtWidgets import QApplication
    # import sys
    # app = QApplication(sys.argv)
    # icon = get_icon("download.png")
    # if icon:
    #     print("Test icon loaded successfully.")
    # else:
    #     print("Test icon failed to load.")
    # sys.exit()
    pass 