import sys
import os

# --- Explicitly modify sys.path ---
script_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.join(script_dir, "src")
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)
print(f"RUN.PY: Modified sys.path: {sys.path}")
# --- End sys.path modification ---

import asyncio
from pathlib import Path
from PyQt6.QtWidgets import QApplication
# Import qasync
import qasync
import logging
from PyQt6.QtCore import QCoreApplication, QTimer
from typing import Dict

# Import MainWindow from the correct location
from src.ui.main_window import MainWindow 

# PRINT THE FILE PATH OF THE MODULE CONTAINING MainWindow
import inspect
module_path = inspect.getfile(MainWindow)
print(f"RUN.PY: MainWindow class is defined in module: {module_path}")

# INTENTIONAL CRASH POINT FOR RUN.PY - REMOVED
# raise Exception("BREAKPOINT_RUN_PY: If you see this, the LATEST run.py is running, AND MainWindow path was printed.")

from src.config_manager import ConfigManager
from src.services.deezer_api import DeezerAPI
from src.services.download_manager import DownloadManager, is_valid_arl
from src.ui.settings_dialog import SettingsDialog
# Import image cache utilities
from src.utils.image_cache import clean_cache

# Set up basic logging for run.py
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
logger = logging.getLogger("run")

# Remove the async run_app function, setup will be synchronous
# async def run_app(): ...

def test_single_download(track_id_to_test: int, app_instance):
    """
    Directly tests downloading a single track using the backend services.
    """
    logger.info(f"--- Starting Direct Download Test for Track ID: {track_id_to_test} ---")

    # 1. Initialize ConfigManager
    config_manager = ConfigManager()
    if not config_manager.config:
        logger.error("TEST: Failed to load configuration. Aborting test.")
        return

    # 2. Initialize DeezerAPI
    loop = asyncio.get_event_loop()

    deezer_api = DeezerAPI(config=config_manager, loop=loop)
    deezer_api.arl = config_manager.get_setting('deezer.arl')
    if not is_valid_arl(deezer_api.arl): # Make sure to import or define is_valid_arl
        logger.error("TEST: ARL token is not valid or not configured. Please set it in settings.json. Aborting test.")
        return
    deezer_api.initialized = True
    logger.info("TEST: DeezerAPI instance created and manually set to initialized=True for test.")


    # 3. Initialize DownloadManager
    download_manager = DownloadManager(config_manager=config_manager, deezer_api=deezer_api)
    logger.info("TEST: DownloadManager initialized for test.")

    # 4. Define dummy signal handlers for testing
    def handle_started(item_id, item_type):
        logger.info(f"TEST SIGNAL - Started: {item_type} {item_id}")

    def handle_progress(item_id, progress):
        logger.info(f"TEST SIGNAL - Progress for {item_id}: {progress:.2f}%")

    def handle_finished(item_id, item_type, file_path):
        logger.info(f"TEST SIGNAL - Finished: {item_type} {item_id} at {file_path}")
        # Quit after the first successful download for a focused test run
        logger.info("TEST: Download finished, quitting test application.")
        app_instance.quit()


    def handle_error(item_id, item_type, error_message):
        logger.error(f"TEST SIGNAL - Error: {item_type} {item_id} - {error_message}")
        logger.info("TEST: Download error, quitting test application.")
        app_instance.quit()

    download_manager.signals.started.connect(handle_started)
    download_manager.signals.progress.connect(handle_progress)
    download_manager.signals.finished.connect(handle_finished)
    download_manager.signals.error.connect(handle_error)

    # 5. Trigger the download
    logger.info(f"TEST: Calling download_track for {track_id_to_test}")
    download_manager.download_track(track_id_to_test)

    logger.info(f"--- Direct Download Test for Track ID: {track_id_to_test} Queued ---")


def main():
    # Option 1: Setup your AppLogging if it configures the root logger
    # AppLogging.setup(level=logging.DEBUG) # Or however your AppLogging is initialized

    # Option 2: Or use basicConfig if AppLogging is not for backend/general logging
    # Ensure this is called only once
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(stream=sys.stdout, level=logging.DEBUG,
                            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    logger.info("--- APPLICATION STARTING ---")

    # Clean the image cache during startup (in a non-blocking way)
    try:
        # Run cache cleanup in a separate thread to avoid blocking startup
        import threading
        cleanup_thread = threading.Thread(target=clean_cache, args=(200, 30))
        cleanup_thread.daemon = True  # Daemon thread will exit when main thread exits
        cleanup_thread.start()
        logger.info("Image cache cleanup started in background thread")
    except Exception as e:
        logger.error(f"Error starting image cache cleanup: {e}")

    app = QApplication(sys.argv)

    # Set up qasync event loop
    event_loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(event_loop)

    # Add a global exception handler for asyncio tasks
    def exception_handler(loop, context):
        exception = context.get('exception')
        if exception:
            logger.error(f"Uncaught exception in asyncio task: {exception}", exc_info=exception)
        else:
            logger.error(f"Error in asyncio event loop: {context['message']}")
    
    event_loop.set_exception_handler(exception_handler)

    # --- UI SECTION ---
    config_manager = ConfigManager() # Create once
    main_window = MainWindow(config_manager) 
    main_window.show()
    
    # Schedule the asynchronous initialization of services
    if hasattr(main_window, 'initialize_services') and asyncio.iscoroutinefunction(main_window.initialize_services):
        logger.info("Scheduling asynchronous initialization of MainWindow services.")
        # Create task on the event_loop which is managed by qasync
        init_task = event_loop.create_task(main_window.initialize_services())
        
        # Add done callback to log any exceptions
        def init_done(task):
            try:
                task.result()  # This will raise any exception from the task
                logger.info("MainWindow services initialized successfully")
                
                # Connect signals after initialization 
                if hasattr(main_window, 'connect_signals'):
                    main_window.connect_signals()
                    logger.info("MainWindow signals connected after initialization")
            except Exception as e:
                logger.error(f"Error during MainWindow initialization: {e}", exc_info=True)
        
        init_task.add_done_callback(init_done)
    else:
        logger.error("MainWindow.initialize_services is not an async method or does not exist!")

    # --- TEST SECTION ---
    # track_to_test_id = 116914118 # Comfortably Numb (Disc 2, Track 6 of The Wall)
    # test_single_download(track_to_test_id, app)
    
    # The app.quit() is now called from handle_finished or handle_error
    # If the download never starts or signals never fire, QTimer can be a fallback.
    # QTimer.singleShot(60000, lambda: (logger.warning("TEST: Timeout reached, quitting."), app.quit()))

    # app.exec() will run the qasync event loop
    with event_loop:
        return_code = event_loop.run_forever()
        
    logger.info(f"--- APPLICATION FINISHED (Exit Code: {return_code}) ---")
    sys.exit(return_code)


if __name__ == "__main__":
    main()