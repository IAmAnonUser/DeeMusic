import sys
import os

# --- Explicitly modify sys.path ---
script_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.join(script_dir, "src")
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)
print(f"RUN.PY: Modified sys.path: {sys.path}")
# --- End sys.path modification ---

# Apply startup optimizations as early as possible (disabled for now)
# try:
#     from src.utils.startup_optimizer import optimize_startup
#     optimize_startup()
#     print("RUN.PY: Startup optimizations applied")
# except ImportError as e:
#     print(f"RUN.PY: Performance optimization modules not available: {e}")
# except Exception as e:
#     print(f"RUN.PY: Warning - Could not apply startup optimizations: {e}")
print("RUN.PY: Startup optimizations disabled for compatibility")

import asyncio
from pathlib import Path
from PyQt6.QtWidgets import QApplication
# Import qasync
import qasync
import logging
from logging.handlers import RotatingFileHandler
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
# Legacy download manager moved to backup
# from src.services.download_manager import DownloadManager, is_valid_arl

# Simple ARL validation function (moved from legacy download_manager)
def is_valid_arl(arl: str) -> bool:
    """Basic check if ARL looks potentially valid."""
    return arl is not None and len(arl) > 100
from src.ui.settings_dialog import SettingsDialog
# Import image cache utilities
from src.utils.image_cache import clean_cache

# Set up basic logging for run.py
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
logger = logging.getLogger("run")

# Initialize rotating file logging early so all modules write to file
def _setup_file_logging():
    try:
        appdata_dir = os.environ.get('APPDATA') or os.path.expanduser('~')
        log_dir = os.path.join(appdata_dir, 'DeeMusic', 'logs')
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, 'deemusic_debug.log')
        file_handler = RotatingFileHandler(log_file, maxBytes=5_000_000, backupCount=3, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s'))
        root_logger = logging.getLogger()
        # Avoid duplicate handlers for the same file
        if not any(isinstance(h, RotatingFileHandler) and getattr(h, 'baseFilename', '') == os.path.abspath(log_file) for h in root_logger.handlers):
            root_logger.addHandler(file_handler)
            # Set to INFO level to reduce startup noise while keeping important logs
            root_logger.setLevel(logging.INFO)
        print(f"RUN.PY: File logging to {log_file}")
    except Exception as e:
        print(f"RUN.PY: Failed to initialize file logging: {e}")

_setup_file_logging()

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


def handle_exception(exc_type, exc_value, exc_traceback):
    """Global exception handler to catch unhandled exceptions."""
    if issubclass(exc_type, KeyboardInterrupt):
        # Allow KeyboardInterrupt to work normally
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    
    # Log the exception
    logger = logging.getLogger(__name__)
    logger.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))
    
    # Also print to stderr for immediate visibility
    print(f"CRITICAL ERROR: {exc_type.__name__}: {exc_value}", file=sys.stderr)
    import traceback
    traceback.print_exception(exc_type, exc_value, exc_traceback, file=sys.stderr)

def main():
    # Set up global exception handler
    sys.excepthook = handle_exception
    
    # PERFORMANCE OPTIMIZATION: Apply startup optimizations for standalone executable
    perf_monitor = None
    try:
        from src.utils.startup_optimizer import apply_startup_optimizations, create_performance_monitor
        optimizer = apply_startup_optimizations()
        perf_monitor = create_performance_monitor()
        if perf_monitor:
            perf_monitor.checkpoint("Startup optimizations applied")
    except Exception as e:
        # Don't let optimization failures break the app
        print(f"Startup optimization warning: {e}")

    # Option 1: Setup your AppLogging if it configures the root logger
    # AppLogging.setup(level=logging.DEBUG) # Or however your AppLogging is initialized

    # Option 2: Or use basicConfig if AppLogging is not for backend/general logging
    # Ensure this is called only once
    if not logging.getLogger().hasHandlers():
        logging.basicConfig(stream=sys.stdout, level=logging.INFO,
                            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Set specific loggers to WARNING/ERROR to reduce startup verbosity
    logging.getLogger('src.services.deezer_api').setLevel(logging.WARNING)
    logging.getLogger('src.services.new_download_worker').setLevel(logging.INFO)
    logging.getLogger('urllib3.connectionpool').setLevel(logging.WARNING)
    logging.getLogger('services.event_bus').setLevel(logging.WARNING)
    logging.getLogger('services.new_download_worker').setLevel(logging.INFO)
    
    # Suppress noisy UI and framework loggers to minimize startup noise
    logging.getLogger('utils.image_cache').setLevel(logging.ERROR)
    logging.getLogger('src.utils.image_cache').setLevel(logging.ERROR)
    logging.getLogger('src.ui.search_widget').setLevel(logging.ERROR)
    logging.getLogger('qasync').setLevel(logging.ERROR)
    logging.getLogger('src.ui.components.responsive_grid').setLevel(logging.ERROR)
    logging.getLogger('src.utils.icon_utils').setLevel(logging.ERROR)
    logging.getLogger('PyQt6').setLevel(logging.ERROR)
    logging.getLogger('asyncio').setLevel(logging.WARNING)
    logging.getLogger('aiohttp').setLevel(logging.WARNING)
    
    # Suppress library scanner excessive logging
    logging.getLogger('src.ui.library_scanner_widget_minimal').setLevel(logging.WARNING)

    logger.info("--- APPLICATION STARTING ---")
    
    if perf_monitor:
        perf_monitor.checkpoint("Logging initialized")

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
    
    # Set up Qt exception handling
    def qt_exception_hook(exc_type, exc_value, exc_traceback):
        """Handle exceptions in Qt slots and callbacks."""
        logger = logging.getLogger(__name__)
        logger.critical("Qt exception", exc_info=(exc_type, exc_value, exc_traceback))
        print(f"QT ERROR: {exc_type.__name__}: {exc_value}", file=sys.stderr)
    
    # Install Qt exception hook
    sys.excepthook = qt_exception_hook
    
    # PERFORMANCE OPTIMIZATION: Apply UI-specific optimizations
    try:
        from src.utils.startup_optimizer import optimize_ui_startup
        optimize_ui_startup(app)
        if perf_monitor:
            perf_monitor.checkpoint("UI optimizations applied")
    except Exception as e:
        logger.warning(f"UI optimization warning: {e}")

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

    # PERFORMANCE MONITORING: Final checkpoint before main loop
    if perf_monitor:
        perf_monitor.checkpoint("Application ready - entering main loop")
        perf_monitor.summary()

    # Set up asyncio exception handler
    def asyncio_exception_handler(loop, context):
        """Handle asyncio exceptions."""
        logger = logging.getLogger(__name__)
        exception = context.get('exception')
        if exception:
            logger.critical(f"Asyncio exception: {exception}", exc_info=exception)
        else:
            logger.critical(f"Asyncio error: {context}")
        print(f"ASYNCIO ERROR: {context}", file=sys.stderr)
    
    event_loop.set_exception_handler(asyncio_exception_handler)
    
    # app.exec() will run the qasync event loop
    with event_loop:
        return_code = event_loop.run_forever()
        
    logger.info(f"--- APPLICATION FINISHED (Exit Code: {return_code}) ---")
    sys.exit(return_code)


if __name__ == "__main__":
    main()