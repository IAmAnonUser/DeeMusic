"""
Main Window for DeeMusic Library Scanner
"""

import os
import logging
from pathlib import Path
from typing import List, Dict, Any
import asyncio
import qasync
import json
import hashlib
from datetime import datetime

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QLabel, QPushButton, QProgressBar, QTextEdit, 
    QTreeWidget, QTreeWidgetItem, QGroupBox, QLineEdit,
    QFileDialog, QMessageBox, QStatusBar, QMenuBar, QMenu,
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter, QSlider, QApplication, QInputDialog, QCheckBox, QProgressDialog
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QIcon, QAction

from core.library_scanner import LibraryScanner, TrackInfo
from core.comparison_engine import ComparisonEngine
from services.deezer_service import DeezerService
from services.download_manager import DownloadManager
from ui.queue_import_dialog import QueueImportDialog
from utils.queue_integration import QueueIntegration

logger = logging.getLogger(__name__)


def trackinfo_to_dict(track):
    """Convert TrackInfo object to dictionary."""
    return {
        "file_path": getattr(track, "file_path", ""),
        "title": getattr(track, "title", ""),
        "artist": getattr(track, "artist", ""),
        "album": getattr(track, "album", ""),
        "album_artist": getattr(track, "album_artist", ""),
        "track_number": getattr(track, "track_number", 0),
        "disc_number": getattr(track, "disc_number", 1),
        "year": getattr(track, "year", 0),
        "duration": getattr(track, "duration", 0),
        "genre": getattr(track, "genre", ""),
        "file_size": getattr(track, "file_size", 0),
        "file_format": getattr(track, "file_format", ""),
        "bitrate": getattr(track, "bitrate", 0),
        "sample_rate": getattr(track, "sample_rate", 0)
    }


class ScanWorker(QThread):
    """Worker thread for scanning library."""
    progress_updated = pyqtSignal(int, int)
    status_updated = pyqtSignal(str)
    scan_completed = pyqtSignal(list)
    scan_cancelled = pyqtSignal()
    
    def __init__(self, config, library_paths, incremental=False, last_scan_timestamp=None, existing_tracks=None):
        super().__init__()
        self.config = config
        self.library_paths = library_paths
        self.incremental = incremental
        self.last_scan_timestamp = last_scan_timestamp
        self.existing_tracks = existing_tracks or []
        self.scanner = LibraryScanner(config)
        self._cancelled = False
    
    def run(self):
        print("ScanWorker run called")
        logger.info("Library Scanner ScanWorker.run() started")
        try:
            self.scanner.set_progress_callback(self.progress_updated.emit)
            self.scanner.set_status_callback(self.status_updated.emit)
            
            if self.incremental:
                # For incremental scans, start with existing tracks
                self.scanner.tracks = self.existing_tracks.copy()
            
            logger.info(f"Starting Library Scanner scan of {len(self.library_paths)} paths")
            tracks = self.scanner.scan_library(
                self.library_paths, 
                incremental=self.incremental, 
                last_scan_timestamp=self.last_scan_timestamp
            )
            
            logger.info(f"Library Scanner scan completed: {len(tracks)} albums found")
            if not self._cancelled:
                logger.info("Emitting scan_completed signal")
                self.scan_completed.emit(tracks)
            else:
                self.scan_cancelled.emit()
                
        except Exception as e:
            print(f"Exception in ScanWorker: {e}")
            import traceback; traceback.print_exc()
            if not self._cancelled:
                self.scan_completed.emit([])
    
    def cancel(self):
        """Cancel the scan."""
        self._cancelled = True
        if hasattr(self.scanner, 'is_scanning'):
            self.scanner.is_scanning = False


class ComparisonWorker(QThread):
    """Worker thread for comparing with Deezer."""
    progress_updated = pyqtSignal(str)
    comparison_completed = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, config, local_tracks):
        super().__init__()
        self.config = config
        self.local_tracks = local_tracks
        
    def run(self):
        """Run the comparison in a separate thread."""
        logger.info("ComparisonWorker.run() started")
        try:
            logger.info("Creating event loop...")
            # Create event loop for async operations
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            logger.info("Running async comparison...")
            # Run the async comparison
            results = loop.run_until_complete(self._run_comparison())
            
            logger.info("Comparison completed, emitting results...")
            self.comparison_completed.emit(results)
            
        except Exception as e:
            logger.error(f"Error during comparison: {e}")
            self.error_occurred.emit(str(e))
        finally:
            logger.info("Closing event loop...")
            loop.close()
            
    async def _run_comparison(self):
        """Run the async comparison."""
        logger.info("_run_comparison() started")
        self.progress_updated.emit("Initializing Deezer connection...")
        
        # Create Deezer service
        arl_token = self.config.get_deezer_arl()
        logger.info(f"Using ARL token: {arl_token[:10]}..." if arl_token else "No ARL token")
        
        logger.info("Creating DeezerService...")
        async with DeezerService(arl_token) as deezer:
            logger.info("DeezerService created successfully")
            # Create comparison engine
            engine = ComparisonEngine(deezer, self.config)
            logger.info("ComparisonEngine created")
            
            self.progress_updated.emit("Starting comparison with Deezer...")
            logger.info(f"Starting comparison with {len(self.local_tracks)} tracks")
            
            # Run comparison
            results = await engine.compare_with_deezer(self.local_tracks)
            logger.info("Comparison completed successfully")
            
            return results


class FastComparisonWorker(QThread):
    progress_updated = pyqtSignal(str, int, int, str)  # artist, idx, total, album
    comparison_completed = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    def __init__(self, config, local_tracks):
        super().__init__()
        self.config = config
        self.local_tracks = local_tracks
    def run(self):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            results = loop.run_until_complete(self._run_comparison())
            self.comparison_completed.emit(results)
        except Exception as e:
            logger.error(f"Error during fast album comparison: {e}")
            self.error_occurred.emit(str(e))
        finally:
            loop.close()
    async def _run_comparison(self):
        arl_token = self.config.get_deezer_arl()
        async with DeezerService(arl_token) as deezer:
            engine = ComparisonEngine(deezer, self.config)
            def progress_callback(artist, idx, total, album):
                self.progress_updated.emit(artist, idx, total, album)
            results = await engine.compare_albums_with_deezer(self.local_tracks, progress_callback=progress_callback)
            return results


class IncrementalFastComparisonWorker(QThread):
    progress_updated = pyqtSignal(str, int, int, str)  # artist, idx, total, album
    comparison_completed = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, config, local_tracks, cached_results):
        super().__init__()
        self.config = config
        self.local_tracks = local_tracks
        self.cached_results = cached_results
    
    def run(self):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            results = loop.run_until_complete(self._run_incremental_comparison())
            self.comparison_completed.emit(results)
        except Exception as e:
            logger.error(f"Error during incremental fast album comparison: {e}")
            self.error_occurred.emit(str(e))
        finally:
            loop.close()
    
    async def _run_incremental_comparison(self):
        arl_token = self.config.get_deezer_arl()
        async with DeezerService(arl_token) as deezer:
            engine = ComparisonEngine(deezer, self.config)
            
            # Get current artists and albums from local tracks
            from collections import defaultdict
            current_albums_by_artist = defaultdict(set)
            for track in self.local_tracks:
                artist = track.get('artist', 'Unknown Artist')
                album = track.get('album', 'Unknown Album')
                if artist != 'Unknown Artist' and album != 'Unknown Album':
                    current_albums_by_artist[artist].add(album)
            
            # Get cached artists
            cached_artists = set(self.cached_results.get('artists', {}).keys())
            current_artists = set(current_albums_by_artist.keys())
            
            # Find new or changed artists
            new_artists = current_artists - cached_artists
            changed_artists = set()
            
            # Check for changed artists (different albums)
            for artist in current_artists & cached_artists:
                cached_albums = set(self.cached_results['artists'][artist].get('local_albums', []))
                current_albums = current_albums_by_artist[artist]
                if cached_albums != current_albums:
                    changed_artists.add(artist)
            
            artists_to_update = new_artists | changed_artists
            
            if not artists_to_update:
                # No changes, return cached results
                return self.cached_results
            
            # Create progress callback
            def progress_callback(artist, idx, total, album):
                self.progress_updated.emit(artist, idx, total, album)
            
            # Only compare new/changed artists
            tracks_for_new_artists = [
                track for track in self.local_tracks
                if track.get('artist') in artists_to_update
            ]
            
            # Run comparison only for new/changed artists
            new_results = await engine.compare_albums_with_deezer(
                tracks_for_new_artists, 
                progress_callback=progress_callback
            )
            
            # Merge results: keep cached results for unchanged artists, add new results
            merged_results = self.cached_results.copy()
            merged_results['artists'].update(new_results['artists'])
            
            # Update statistics
            merged_results['statistics']['total_artists'] = len(merged_results['artists'])
            merged_results['statistics']['total_local_albums'] = sum(
                len(artist_info.get('local_albums', [])) 
                for artist_info in merged_results['artists'].values()
            )
            merged_results['statistics']['total_deezer_albums'] = sum(
                len(artist_info.get('deezer_albums', [])) 
                for artist_info in merged_results['artists'].values()
            )
            merged_results['statistics']['total_missing_albums'] = sum(
                len(artist_info.get('missing_albums', [])) 
                for artist_info in merged_results['artists'].values()
            )
            
            return merged_results


class AddAlbumsToQueueWorker(QThread):
    progress_updated = pyqtSignal(int, int)  # current, total
    queue_completed = pyqtSignal(int, int)   # total_tracks, total_albums
    error_occurred = pyqtSignal(str)
    debug_message = pyqtSignal(str)

    def __init__(self, download_manager, checked_albums, arl_token, parent=None):
        super().__init__(parent)
        self.download_manager = download_manager
        self.checked_albums = checked_albums
        self.arl_token = arl_token

    def run(self):
        import asyncio
        try:
            asyncio.run(self._run_async())
        except Exception as e:
            logging.exception("Exception in AddAlbumsToQueueWorker:")
            self.error_occurred.emit(str(e))

    async def _run_async(self):
        from services.deezer_service import DeezerService
        import asyncio
        
        total_tracks = 0
        total_albums = len(self.checked_albums)
        
        # CRITICAL FIX: Add batch processing to prevent queue overload
        BATCH_SIZE = 10  # Process 10 albums at a time
        BATCH_DELAY = 2.0  # 2 second delay between batches
        
        self.debug_message.emit(f"Processing {total_albums} albums in batches of {BATCH_SIZE} to prevent queue overload")
        
        async with DeezerService(self.arl_token) as deezer:
            for batch_start in range(0, total_albums, BATCH_SIZE):
                batch_end = min(batch_start + BATCH_SIZE, total_albums)
                batch_albums = self.checked_albums[batch_start:batch_end]
                
                self.debug_message.emit(f"Processing batch {batch_start//BATCH_SIZE + 1}/{(total_albums + BATCH_SIZE - 1)//BATCH_SIZE} ({len(batch_albums)} albums)")
                
                # Process current batch
                for i, album_info in enumerate(batch_albums):
                    global_index = batch_start + i
                    artist = album_info['artist']
                    album = album_info['album']
                    
                    try:
                        deezer_album = await deezer.search_album(album, artist)
                        if deezer_album:
                            album_id = deezer_album['id']
                            tracks = await deezer.get_album_tracks(album_id)
                            album_tracks = []
                            for track in tracks:
                                track_info = {
                                    'deezer_track': track,
                                    'artist': artist,
                                    'album': album
                                }
                                album_tracks.append(track_info)
                            # Add the whole album as one entry
                            added_count = self.download_manager.add_album_to_queue(album_tracks)
                            total_tracks += added_count
                            self.debug_message.emit(f"Added {added_count} tracks for album {album} by {artist}")
                        else:
                            self.debug_message.emit(f"No Deezer album found for {album} by {artist}")
                    except Exception as e:
                        logging.exception(f"Error adding album {album} by {artist} to queue:")
                        self.debug_message.emit(f"Error adding album {album} by {artist}: {e}")
                    
                    self.progress_updated.emit(global_index + 1, total_albums)
                
                # Add delay between batches to prevent overwhelming the queue
                if batch_end < total_albums:  # Don't delay after the last batch
                    self.debug_message.emit(f"Batch complete. Waiting {BATCH_DELAY}s before next batch to prevent queue overload...")
                    await asyncio.sleep(BATCH_DELAY)
        
        self.debug_message.emit(f"All batches complete. Total: {total_tracks} tracks from {total_albums} albums")
        self.queue_completed.emit(total_tracks, total_albums)


class MainWindow(QMainWindow):
    """Main window for the Library Scanner application."""
    
    def __init__(self, config):
        super().__init__()
        self.config = config
        
        # Data
        self.local_albums = []
        self.comparison_results = {}
        
        # Workers
        self.scan_worker = None
        self.comparison_worker = None
        
        # Services
        self.download_manager = DownloadManager(config.get_deemusic_path(), config.config_dir)
        
        self.init_ui()
        self.load_settings()
        self.load_saved_scan_results()
        self.load_saved_fast_comparison_results()  # Ensure fast comparison results are loaded on startup
        # Connect tab change to reload cached results if needed
        self.tab_widget.currentChanged.connect(self.on_tab_changed)
    
    def on_tab_changed(self, index):
        # If user switches to Comparison tab and nothing is loaded, try loading cached results
        tab_text = self.tab_widget.tabText(index)
        if tab_text == "Comparison":
            if (not hasattr(self, 'fast_comparison_results') or not self.fast_comparison_results or
                (hasattr(self, 'artists_tree') and self.artists_tree.topLevelItemCount() == 0)):
                self.load_saved_fast_comparison_results()

    def init_ui(self):
        """Initialize the user interface."""
        self.setWindowTitle("DeeMusic Library Scanner v1.0.0")
        self.setGeometry(100, 100, 1200, 800)
        
        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Create main layout
        main_layout = QVBoxLayout(central_widget)
        
        # Create tab widget
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)
        
        # Create tabs
        self.create_library_tab()
        self.create_comparison_tab()
        self.create_download_tab()
        self.create_settings_tab()
        
        # Create status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready - DeeMusic Library Scanner")
    
    def create_library_tab(self):
        """Create the library tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Welcome message
        welcome_label = QLabel("Welcome to DeeMusic Library Scanner!")
        welcome_label.setStyleSheet("font-size: 16px; font-weight: bold; margin: 10px;")
        layout.addWidget(welcome_label)
        
        # Library paths section
        paths_group = QGroupBox("Library Paths")
        paths_layout = QVBoxLayout(paths_group)
        
        # Path controls
        path_controls = QHBoxLayout()
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("Enter library path...")
        
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self.browse_library_path)
        
        add_path_btn = QPushButton("Add Path")
        add_path_btn.clicked.connect(self.add_library_path)
        
        path_controls.addWidget(self.path_input)
        path_controls.addWidget(browse_btn)
        path_controls.addWidget(add_path_btn)
        
        paths_layout.addLayout(path_controls)
        
        # Paths list
        self.paths_list = QTreeWidget()
        self.paths_list.setHeaderLabel("Configured Library Paths")
        paths_layout.addWidget(self.paths_list)
        
        # Remove path button
        remove_path_btn = QPushButton("Remove Selected Path")
        remove_path_btn.clicked.connect(self.remove_library_path)
        paths_layout.addWidget(remove_path_btn)
        
        layout.addWidget(paths_group)
        
        # Scan section
        scan_group = QGroupBox("Library Scan")
        scan_layout = QVBoxLayout(scan_group)
        
        # Scan buttons
        scan_buttons_layout = QHBoxLayout()
        
        self.scan_btn = QPushButton("Full Scan")
        self.scan_btn.clicked.connect(self.scan_library)
        scan_buttons_layout.addWidget(self.scan_btn)
        
        self.update_scan_btn = QPushButton("Update Scan")
        self.update_scan_btn.clicked.connect(self.update_scan_library)
        self.update_scan_btn.setEnabled(False)
        self.update_scan_btn.setToolTip("Scan for new files added since last scan")
        scan_buttons_layout.addWidget(self.update_scan_btn)
        
        self.clear_results_btn = QPushButton("Clear Results")
        self.clear_results_btn.clicked.connect(self.clear_scan_results)
        self.clear_results_btn.setEnabled(False)
        scan_buttons_layout.addWidget(self.clear_results_btn)
        
        scan_layout.addLayout(scan_buttons_layout)
        
        # Progress section
        progress_container = QWidget()
        progress_layout = QVBoxLayout(progress_container)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        
        # Progress bar with enhanced styling
        self.scan_progress = QProgressBar()
        self.scan_progress.setVisible(False)
        self.scan_progress.setStyleSheet("""
            QProgressBar {
                border: 2px solid #cccccc;
                border-radius: 5px;
                text-align: center;
                font-weight: bold;
                background-color: #f0f0f0;
                min-height: 25px;
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
                border-radius: 3px;
            }
        """)
        progress_layout.addWidget(self.scan_progress)
        
        # Progress info row
        progress_info_layout = QHBoxLayout()
        
        # Progress percentage
        self.progress_percentage = QLabel("")
        self.progress_percentage.setVisible(False)
        self.progress_percentage.setStyleSheet("font-weight: bold; color: #333;")
        progress_info_layout.addWidget(self.progress_percentage)
        
        progress_info_layout.addStretch()
        
        # File count
        self.file_count_label = QLabel("")
        self.file_count_label.setVisible(False)
        self.file_count_label.setStyleSheet("color: #666;")
        progress_info_layout.addWidget(self.file_count_label)
        
        # Cancel button
        self.cancel_scan_btn = QPushButton("Cancel")
        self.cancel_scan_btn.clicked.connect(self.cancel_scan)
        self.cancel_scan_btn.setVisible(False)
        self.cancel_scan_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                border: none;
                padding: 5px 15px;
                border-radius: 3px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #da190b;
            }
        """)
        progress_info_layout.addWidget(self.cancel_scan_btn)
        
        progress_layout.addLayout(progress_info_layout)
        scan_layout.addWidget(progress_container)
        
        # Scan status
        self.scan_status = QLabel("Ready to scan - Add library paths above")
        self.scan_status.setStyleSheet("padding: 5px; color: #555;")
        scan_layout.addWidget(self.scan_status)
        
        layout.addWidget(scan_group)
        
        self.tab_widget.addTab(tab, "Library")
    
    def create_comparison_tab(self):
        """Create the comparison tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Info and controls
        info_layout = QHBoxLayout()
        info_label = QLabel("Compare your library with Deezer to find missing tracks or albums")
        info_label.setStyleSheet("font-size: 14px; margin: 10px;")
        info_layout.addWidget(info_label)
        info_layout.addStretch()
        self.fast_compare_btn = QPushButton("Fast Album Comparison")
        self.fast_compare_btn.clicked.connect(self.fast_compare_with_deezer)
        self.fast_compare_btn.setEnabled(False)
        self.fast_compare_btn.setStyleSheet("QPushButton { padding: 8px 16px; font-weight: bold; }")
        info_layout.addWidget(self.fast_compare_btn)
        
        self.update_fast_comparison_btn = QPushButton("Update Fast Comparison")
        self.update_fast_comparison_btn.clicked.connect(self.update_fast_comparison)
        self.update_fast_comparison_btn.setEnabled(False)
        self.update_fast_comparison_btn.setStyleSheet("QPushButton { padding: 8px 16px; font-weight: bold; }")
        self.update_fast_comparison_btn.setToolTip("Update fast album comparison for new/changed artists only")
        info_layout.addWidget(self.update_fast_comparison_btn)
        # Add Re-evaluate with New Settings button
        self.reevaluate_btn = QPushButton("Re-evaluate with New Settings")
        self.reevaluate_btn.clicked.connect(self.reevaluate_with_new_settings)
        self.reevaluate_btn.setStyleSheet("QPushButton { padding: 8px 16px; font-weight: bold; }")
        info_layout.addWidget(self.reevaluate_btn)
        # Add Clear Cache button
        self.clear_cache_btn = QPushButton("Clear Cache")
        self.clear_cache_btn.clicked.connect(self.clear_comparison_cache)
        self.clear_cache_btn.setStyleSheet("QPushButton { padding: 8px 16px; font-weight: bold; }")
        info_layout.addWidget(self.clear_cache_btn)
        # Add Debug Partial Re-evaluation button
        self.debug_reevaluate_btn = QPushButton("Debug Partial Re-evaluation")
        self.debug_reevaluate_btn.clicked.connect(self.debug_reevaluate_with_new_settings)
        self.debug_reevaluate_btn.setStyleSheet("QPushButton { padding: 8px 16px; font-weight: bold; }")
        info_layout.addWidget(self.debug_reevaluate_btn)
        # Add Exclude Live Albums checkbox
        self.exclude_live_checkbox = QCheckBox("Exclude Live Albums")
        self.exclude_live_checkbox.setToolTip("If checked, albums with 'live' in the album or artist name will be excluded from comparison scans.")
        info_layout.addWidget(self.exclude_live_checkbox)
        # Connect checkbox to refresh albums tree
        self.exclude_live_checkbox.stateChanged.connect(self.on_exclude_live_albums_changed)
        # Add Exclude Alternate Versions checkbox
        self.exclude_alternate_checkbox = QCheckBox("Hide Alternates if Any Version Owned")
        self.exclude_alternate_checkbox.setToolTip("If checked, missing albums that are alternate versions (e.g., Deluxe, Remaster) will be hidden if you already own any version of that album.")
        info_layout.addWidget(self.exclude_alternate_checkbox)
        self.exclude_alternate_checkbox.setChecked(False)
        # Connect to refresh albums tree
        self.exclude_alternate_checkbox.stateChanged.connect(self.on_exclude_live_albums_changed)
        layout.addLayout(info_layout)
        self.comparison_progress = QProgressBar()
        self.comparison_progress.setVisible(False)
        layout.addWidget(self.comparison_progress)
        self.comparison_status_label = QLabel("")
        self.comparison_status_label.setVisible(False)
        layout.addWidget(self.comparison_status_label)
        self.results_tabs = QTabWidget()
        self.summary_text = QTextEdit()
        self.summary_text.setReadOnly(True)
        self.results_tabs.addTab(self.summary_text, "Summary")
        # Create hierarchical view for missing albums
        self.missing_albums_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left side: Artists tree
        self.artists_tree = QTreeWidget()
        self.artists_tree.setHeaderLabels(["Artist", "Missing Albums"])
        self.artists_tree.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        self.artists_tree.setSortingEnabled(True)
        self.artists_tree.setColumnCount(2)
        self.artists_tree.sortItems(0, Qt.SortOrder.AscendingOrder)  # Sort A-Z by artist name
        self.artists_tree.setColumnWidth(0, 220)  # Wider artist column
        self.artists_tree.setColumnWidth(1, 120)  # Wider missing albums column
        self.artists_tree.itemClicked.connect(self.on_artist_selected)
        self.artists_tree.itemChanged.connect(self.on_artist_checkbox_changed)
        
        # Right side: Albums tree
        self.albums_tree = QTreeWidget()
        self.albums_tree.setHeaderLabels(["Album", "Artist"])
        self.albums_tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.albums_tree.setSortingEnabled(True)
        self.albums_tree.setColumnCount(2)
        self.albums_tree.setColumnWidth(0, 320)  # Wider album column
        self.albums_tree.setColumnWidth(1, 180)  # Wider artist column
        self.albums_tree.sortItems(0, Qt.SortOrder.AscendingOrder)  # Sort A-Z by album name
        self.albums_tree.itemChanged.connect(self.on_album_checkbox_changed)
        
        # Add trees to splitter
        self.missing_albums_splitter.addWidget(self.artists_tree)
        self.missing_albums_splitter.addWidget(self.albums_tree)
        
        # Set initial splitter sizes (artists take 40%, albums take 60%)
        self.missing_albums_splitter.setSizes([400, 600])
        
        layout.addWidget(self.results_tabs)
        
        # Add action buttons
        action_buttons_layout = QHBoxLayout()
        
        # Check All for Artist button
        self.check_all_artist_btn = QPushButton("Check All for Artist")
        self.check_all_artist_btn.clicked.connect(self.check_all_albums_for_artist)
        action_buttons_layout.addWidget(self.check_all_artist_btn)
        
        # Check All Albums button
        self.check_all_albums_btn = QPushButton("Check All Albums")
        self.check_all_albums_btn.clicked.connect(self.check_all_albums)
        action_buttons_layout.addWidget(self.check_all_albums_btn)
        
        # Uncheck All button
        self.uncheck_all_btn = QPushButton("Uncheck All")
        self.uncheck_all_btn.clicked.connect(self.uncheck_all_items)
        action_buttons_layout.addWidget(self.uncheck_all_btn)
        
        action_buttons_layout.addStretch()
        layout.addLayout(action_buttons_layout)
        
        self.results_tabs.addTab(self.missing_albums_splitter, "Missing Albums (Hierarchical)")
        
        # Queue import section
        queue_import_layout = QHBoxLayout()
        
        # Import to DeeMusic button (new primary action)
        self.import_to_deemusic_btn = QPushButton("📤 Import Selected to DeeMusic")
        self.import_to_deemusic_btn.clicked.connect(self.import_selected_to_deemusic)
        self.import_to_deemusic_btn.setEnabled(False)
        self.import_to_deemusic_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 5px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)
        queue_import_layout.addWidget(self.import_to_deemusic_btn)
        
        queue_import_layout.addStretch()
        
        # Legacy queue buttons (kept for compatibility)
        self.add_selected_albums_btn = QPushButton("Add Selected Albums to Queue")
        self.add_selected_albums_btn.clicked.connect(self.add_selected_albums_to_queue)
        self.add_selected_albums_btn.setEnabled(True)
        queue_import_layout.addWidget(self.add_selected_albums_btn)
        
        layout.addLayout(queue_import_layout)
        
        # Legacy action layout (kept for compatibility)
        action_layout = QHBoxLayout()
        self.add_all_missing_btn = QPushButton("Add All Missing to Queue")
        self.add_all_missing_btn.clicked.connect(self.add_all_missing_to_queue)
        self.add_all_missing_btn.setEnabled(False)
        self.add_selected_btn = QPushButton("Add Selected to Queue")
        self.add_selected_btn.clicked.connect(self.add_selected_to_queue)
        self.add_selected_btn.setEnabled(False)
        action_layout.addWidget(self.add_all_missing_btn)
        action_layout.addWidget(self.add_selected_btn)
        action_layout.addStretch()
        layout.addLayout(action_layout)
        self.tab_widget.addTab(tab, "Comparison")

    def create_download_tab(self):
        """Create the download tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        info_label = QLabel("Missing items will be listed here after comparison.")
        info_label.setStyleSheet("font-size: 14px; margin: 10px;")
        layout.addWidget(info_label)
        
        # Download buttons
        download_controls = QHBoxLayout()
        
        self.download_selected_btn = QPushButton("Download Selected")
        self.download_selected_btn.clicked.connect(self.download_selected_items)
        self.download_selected_btn.setEnabled(False)
        
        self.launch_deemusic_btn = QPushButton("Launch DeeMusic")
        self.launch_deemusic_btn.clicked.connect(self.launch_deemusic)
        
        download_controls.addWidget(self.download_selected_btn)
        download_controls.addWidget(self.launch_deemusic_btn)
        download_controls.addStretch()
        
        # Add toggle for album/track view
        self.queue_view_toggle_btn = QPushButton("Show Tracks")
        self.queue_view_toggle_btn.setCheckable(True)
        self.queue_view_toggle_btn.setChecked(False)
        self.queue_view_toggle_btn.toggled.connect(self.on_queue_view_toggle)
        download_controls.addWidget(self.queue_view_toggle_btn)
        
        # Add refresh queue button
        self.refresh_queue_btn = QPushButton("Refresh Queue")
        self.refresh_queue_btn.clicked.connect(self.refresh_download_queue)
        download_controls.addWidget(self.refresh_queue_btn)
        
        layout.addLayout(download_controls)
        
        # Missing items area
        self.missing_items_text = QTextEdit()
        self.missing_items_text.setPlaceholderText("Missing items will be listed here...")
        layout.addWidget(self.missing_items_text)
        
        self.tab_widget.addTab(tab, "Downloads")
        self.queue_album_view = True  # Default to album view
    
    def on_queue_view_toggle(self, checked):
        if checked:
            self.queue_album_view = False
            self.queue_view_toggle_btn.setText("Show Albums")
        else:
            self.queue_album_view = True
            self.queue_view_toggle_btn.setText("Show Tracks")
        self.update_download_tab()
    
    def create_settings_tab(self):
        """Create the settings tab."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # DeeMusic settings
        deemusic_group = QGroupBox("DeeMusic Integration")
        deemusic_layout = QVBoxLayout(deemusic_group)
        
        # DeeMusic path
        path_layout = QHBoxLayout()
        path_layout.addWidget(QLabel("DeeMusic Path:"))
        self.deemusic_path_input = QLineEdit()
        self.deemusic_path_input.setText(self.config.get_deemusic_path())
        
        browse_deemusic_btn = QPushButton("Browse")
        browse_deemusic_btn.clicked.connect(self.browse_deemusic_path)
        
        path_layout.addWidget(self.deemusic_path_input)
        path_layout.addWidget(browse_deemusic_btn)
        
        deemusic_layout.addLayout(path_layout)
        
        layout.addWidget(deemusic_group)
        
        # Deezer settings
        deezer_group = QGroupBox("Deezer Settings")
        deezer_layout = QVBoxLayout(deezer_group)
        
        # ARL token
        arl_layout = QHBoxLayout()
        arl_layout.addWidget(QLabel("ARL Token:"))
        self.arl_input = QLineEdit()
        self.arl_input.setText(self.config.get_deezer_arl())
        self.arl_input.setEchoMode(QLineEdit.EchoMode.Password)
        arl_layout.addWidget(self.arl_input)
        
        deezer_layout.addLayout(arl_layout)
        
        layout.addWidget(deezer_group)
        
        # Album match threshold slider
        threshold_group = QGroupBox("Album Match Threshold")
        threshold_layout = QVBoxLayout(threshold_group)
        threshold_slider_layout = QHBoxLayout()
        self.album_threshold_label = QLabel()
        self.album_threshold_slider = QSlider(Qt.Orientation.Horizontal)
        self.album_threshold_slider.setMinimum(50)
        self.album_threshold_slider.setMaximum(100)
        self.album_threshold_slider.setTickInterval(1)
        self.album_threshold_slider.setSingleStep(1)
        self.album_threshold_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.album_threshold_slider.valueChanged.connect(self.on_album_threshold_changed)
        # Set initial value from config
        threshold = self.config.get_album_match_threshold() if hasattr(self.config, 'get_album_match_threshold') else 75
        self.album_threshold_slider.setValue(threshold)
        self.album_threshold_label.setText(f"{threshold}%")
        threshold_slider_layout.addWidget(QLabel("Fuzzy Match Threshold:"))
        threshold_slider_layout.addWidget(self.album_threshold_slider)
        threshold_slider_layout.addWidget(self.album_threshold_label)
        threshold_layout.addLayout(threshold_slider_layout)
        layout.addWidget(threshold_group)
        
        # Save settings button
        save_btn = QPushButton("Save Settings")
        save_btn.clicked.connect(self.save_settings)
        layout.addWidget(save_btn)
        
        layout.addStretch()
        
        self.tab_widget.addTab(tab, "Settings")
    
    def on_album_threshold_changed(self, value):
        self.album_threshold_label.setText(f"{value}%")
    
    def cancel_scan(self):
        """Cancel the current scan."""
        if self.scan_worker and self.scan_worker.isRunning():
            self.scan_worker.cancel()
            self.scan_worker.wait()
    
    def on_scan_cancelled(self):
        """Handle scan cancellation."""
        # Reset UI state
        self.scan_btn.setEnabled(True)
        # Re-enable update scan button if we have existing results
        if self.local_albums:
            self.update_scan_btn.setEnabled(True)
        self.scan_progress.setVisible(False)
        self.progress_percentage.setVisible(False)
        self.file_count_label.setVisible(False)
        self.cancel_scan_btn.setVisible(False)
        self.scan_status.setText("Scan cancelled by user")
        
        # Show status message
        self.status_bar.showMessage("Library scan cancelled", 3000)
    
    def browse_library_path(self):
        """Browse for library path."""
        path = QFileDialog.getExistingDirectory(self, "Select Library Path")
        if path:
            self.path_input.setText(path)
    
    def add_library_path(self):
        """Add library path."""
        path = self.path_input.text().strip()
        if path and Path(path).exists():
            self.config.add_library_path(path)
            self.update_paths_list()
            self.path_input.clear()
            self.scan_status.setText("Library path added - Ready to scan")
        else:
            QMessageBox.warning(self, "Invalid Path", "Please enter a valid directory path.")
    
    def remove_library_path(self):
        """Remove selected library path."""
        current_item = self.paths_list.currentItem()
        if current_item:
            path = current_item.text(0)
            self.config.remove_library_path(path)
            self.update_paths_list()
    
    def update_paths_list(self):
        """Update the paths list widget."""
        self.paths_list.clear()
        for path in self.config.get_library_paths():
            item = QTreeWidgetItem([path])
            self.paths_list.addTopLevelItem(item)
    
    def scan_library(self):
        """Start library scan."""
        library_paths = self.config.get_library_paths()
        if not library_paths:
            QMessageBox.warning(self, "No Library Paths", "Please add at least one library path.")
            return
        
        # Update UI for scanning state
        self.scan_btn.setEnabled(False)
        self.scan_progress.setVisible(True)
        self.progress_percentage.setVisible(True)
        self.file_count_label.setVisible(True)
        self.cancel_scan_btn.setVisible(True)
        self.scan_status.setText("Starting scan...")
        
        # Reset progress bar
        self.scan_progress.setValue(0)
        self.scan_progress.setMaximum(100)
        self.progress_percentage.setText("0%")
        self.file_count_label.setText("0 / 0 files")
        
        # Start scan worker
        self.scan_worker = ScanWorker(self.config, library_paths)
        self.scan_worker.progress_updated.connect(self.update_scan_progress)
        self.scan_worker.status_updated.connect(self.update_scan_status)
        self.scan_worker.scan_completed.connect(self.on_scan_completed)
        self.scan_worker.scan_cancelled.connect(self.on_scan_cancelled)
        self.scan_worker.start()
    
    def update_scan_library(self):
        """Start incremental library scan for new files."""
        library_paths = self.config.get_library_paths()
        if not library_paths:
            QMessageBox.warning(self, "No Library Paths", "Please add at least one library path.")
            return
        
        # Get last scan timestamp
        scan_info = self.config.get_scan_results_info()
        if not scan_info or not scan_info.get('scan_timestamp'):
            QMessageBox.warning(self, "No Previous Scan", 
                              "No previous scan found. Please run a full scan first.")
            return
        
        last_scan_timestamp = scan_info['scan_timestamp']
        
        # Update UI for scanning state
        self.scan_btn.setEnabled(False)
        self.update_scan_btn.setEnabled(False)
        self.scan_progress.setVisible(True)
        self.progress_percentage.setVisible(True)
        self.file_count_label.setVisible(True)
        self.cancel_scan_btn.setVisible(True)
        self.scan_status.setText("Starting incremental scan...")
        
        # Reset progress bar
        self.scan_progress.setValue(0)
        self.scan_progress.setMaximum(100)
        self.progress_percentage.setText("0%")
        self.file_count_label.setText("0 / 0 files")
        
        # Start incremental scan worker
        self.scan_worker = ScanWorker(
            self.config, 
            library_paths, 
            incremental=True, 
            last_scan_timestamp=last_scan_timestamp,
            existing_tracks=self.local_albums
        )
        self.scan_worker.progress_updated.connect(self.update_scan_progress)
        self.scan_worker.status_updated.connect(self.update_scan_status)
        self.scan_worker.scan_completed.connect(self.on_update_scan_completed)
        self.scan_worker.scan_cancelled.connect(self.on_scan_cancelled)
        self.scan_worker.start()
    
    def update_scan_progress(self, current: int, total: int):
        """Update scan progress."""
        if total > 0:
            # Update progress bar
            self.scan_progress.setMaximum(total)
            self.scan_progress.setValue(current)
            
            # Update percentage
            percentage = int((current / total) * 100)
            self.progress_percentage.setText(f"{percentage}%")
            
            # Update file count
            self.file_count_label.setText(f"{current} / {total} files")
            
            # Update progress bar text
            self.scan_progress.setFormat(f"{current}/{total} files processed ({percentage}%)")
        else:
            # Initial state or unknown total
            self.scan_progress.setMaximum(0)  # Indeterminate progress
            self.progress_percentage.setText("0%")
            self.file_count_label.setText("Scanning...")
            self.scan_progress.setFormat("Scanning directories...")
    
    def update_scan_status(self, status: str):
        """Update scan status."""
        self.scan_status.setText(status)
    
    def on_scan_completed(self, albums: List[Dict]):
        """Handle scan completion."""
        logger.info(f"on_scan_completed called with {len(albums)} albums")
        self.local_albums = albums
        self.scan_btn.setEnabled(True)
        # Hide progress elements
        self.scan_progress.setVisible(False)
        self.progress_percentage.setVisible(False)
        self.file_count_label.setVisible(False)
        self.cancel_scan_btn.setVisible(False)
        # Remove compare_btn reference
        self.fast_compare_btn.setEnabled(True)
        self.clear_results_btn.setEnabled(True)
        self.update_scan_btn.setEnabled(True)
        # Save scan results to disk
        self.save_scan_results(albums)
        # Update stats for album-level data
        artists = set(album['album_artist'] for album in albums)
        total_tracks = sum(album['num_tracks'] for album in albums)
        stats_text = f"Scan completed! Found {len(albums)} albums from {len(artists)} artists ({total_tracks} total tracks)"
        self.scan_status.setText(stats_text)
        QMessageBox.information(self, "Scan Complete", 
                              f"Library scan completed successfully!\n\n"
                              f"\U0001F4C1 Found: {len(albums)} albums\n"
                              f"\U0001F3A4 Artists: {len(artists)}\n"
                              f"\U0001F4BF Total tracks: {total_tracks}\n\n"
                              "Results saved for next session!\n"
                              "You can now compare with Deezer!")
    
    def on_update_scan_completed(self, albums: List[Dict]):
        """Handle incremental scan completion."""
        # Calculate new albums found
        original_count = len(self.local_albums)
        new_count = len(albums) - original_count
        self.local_albums = albums
        self.scan_btn.setEnabled(True)
        self.update_scan_btn.setEnabled(True)
        # Hide progress elements
        self.scan_progress.setVisible(False)
        self.progress_percentage.setVisible(False)
        self.file_count_label.setVisible(False)
        self.cancel_scan_btn.setVisible(False)
        # Remove compare_btn reference
        self.fast_compare_btn.setEnabled(True)
        self.clear_results_btn.setEnabled(True)
        # Save updated scan results to disk
        self.save_scan_results(albums)
        # Update stats for album-level data
        artists = set(album['album_artist'] for album in albums)
        total_tracks = sum(album['num_tracks'] for album in albums)
        stats_text = f"Update scan completed! Found {new_count} new albums. Total: {len(albums)} albums from {len(artists)} artists ({total_tracks} total tracks)"
        self.scan_status.setText(stats_text)
        if new_count > 0:
            QMessageBox.information(self, "Update Scan Complete", 
                                  f"Incremental scan completed successfully!\n\n"
                                  f"\U0001F195 New albums found: {new_count}\n"
                                  f"\U0001F4C1 Total albums: {len(albums)}\n"
                                  f"\U0001F3A4 Artists: {len(artists)}\n"
                                  f"\U0001F4BF Total tracks: {total_tracks}\n\n"
                                  "Results updated and saved!")
        else:
            QMessageBox.information(self, "Update Scan Complete", 
                                  f"Incremental scan completed!\n\n"
                                  f"No new albums found since last scan.\n"
                                  f"Your library is up to date.\n\n"
                                  f"\U0001F4C1 Total albums: {len(albums)}\n"
                                  f"\U0001F3A4 Artists: {len(artists)}\n"
                                  f"\U0001F4BF Total tracks: {total_tracks}")
    
    def compare_with_deezer(self):
        """Start comparison with Deezer."""
        print("=== COMPARE WITH DEEZER METHOD CALLED ===")
        try:
            print("=== INSIDE TRY BLOCK ===")
            logger.info("Compare with Deezer button clicked!")
            
            logger.info("Checking Deezer ARL token...")
            arl_token = self.config.get_deezer_arl()
            print(f"=== ARL TOKEN: {bool(arl_token)} ===")
            logger.info(f"ARL token check result: {bool(arl_token)}")
            
            if not arl_token:
                logger.warning("No Deezer ARL token configured")
                QMessageBox.warning(self, "No ARL Token", "Please set your Deezer ARL token in Settings.")
                return
            logger.info("Deezer ARL token check passed")
        
        try:
            logger.info("Checking local albums data...")
            logger.info(f"self.local_albums type: {type(self.local_albums)}")
            logger.info(f"self.local_albums length: {len(self.local_albums) if self.local_albums else 'None'}")
        except Exception as e:
            logger.error(f"Error checking local albums: {e}")
            return
        
        if not self.local_albums:
            logger.warning("No local albums data available")
            QMessageBox.warning(self, "No Library Data", 
                              "No library scan data found. Please scan your library using the 'Scan Library' button above before running a comparison.")
            return
        logger.info(f"Local albums available: {len(self.local_albums)}")
        
        # Filter albums to only include those from currently configured library paths
        # First try to get library paths from current config
        library_paths = self.config.get_library_paths()
        
        # If no current paths, try to get them from the scan results
        if not library_paths:
            scan_data = self.config.load_scan_results()
            if scan_data and scan_data.get('library_paths'):
                library_paths = scan_data['library_paths']
                logger.info(f"Using library paths from scan results: {library_paths}")
            else:
                logger.warning("No library paths configured and none found in scan results")
                QMessageBox.warning(self, "No Library Paths", 
                                  "No library paths configured. Please add library paths in the Library Paths section above, "
                                  "or re-scan your library to update the configuration.")
                return
        else:
            logger.info(f"Using configured library paths: {library_paths}")
            
        # Only include albums whose folder_path is within the configured library paths
        albums = []
        for album in self.local_albums:
            folder_path = album.get('folder_path', '')
            if folder_path:
                # Normalize paths for comparison (handle Windows path separators and case)
                folder_path_normalized = os.path.normpath(folder_path).lower()
                # Check if this album's folder is within any of the configured library paths
                for lib_path in library_paths:
                    lib_path_normalized = os.path.normpath(lib_path).lower()
                    if folder_path_normalized.startswith(lib_path_normalized):
                        albums.append(album)
                        break
        
        if not albums:
            QMessageBox.warning(self, "No Albums Found", 
                              "No albums found in the currently configured library paths. "
                              "Please check your library path configuration.")
            return
        
        # Exclude live albums if checkbox is checked
        if hasattr(self, 'exclude_live_checkbox') and self.exclude_live_checkbox.isChecked():
            albums = [a for a in albums if 'live' not in (a.get('album', '') or '').lower() and 'live' not in (a.get('album_artist', '') or '').lower()]
        
        logger.info(f"Albums after filtering: {len(albums)}")
        logger.info("Converting albums to tracks for comparison...")
        try:
            tracks_for_comparison = [trackinfo_to_dict(t) if not isinstance(t, dict) else t for t in albums]
            logger.info(f"Tracks for comparison: {len(tracks_for_comparison)}")
        except Exception as e:
            logger.error(f"Error converting albums to tracks: {e}")
            QMessageBox.critical(self, "Conversion Error", f"Error preparing data for comparison: {e}")
            return
        logger.info("Starting comparison worker...")
        logger.info("Setting up UI for comparison...")
        self.compare_btn.setEnabled(False)
        self.comparison_progress.setVisible(True)
        self.comparison_progress.setMaximum(0)  # Indeterminate
        
        logger.info("Creating comparison worker...")
        try:
            self.comparison_worker = ComparisonWorker(self.config, tracks_for_comparison)
            self.comparison_worker.progress_updated.connect(self.update_comparison_progress)
            self.comparison_worker.comparison_completed.connect(self.on_comparison_completed)
            self.comparison_worker.error_occurred.connect(self.on_comparison_error)
            logger.info("Starting comparison worker thread...")
            self.comparison_worker.start()
            logger.info("Comparison worker started successfully!")
        except Exception as e:
            logger.error(f"Error creating or starting comparison worker: {e}")
            QMessageBox.critical(self, "Worker Error", f"Error starting comparison: {e}")
            self.compare_btn.setEnabled(True)
            self.comparison_progress.setVisible(False)
            
        except Exception as e:
            logger.error(f"Unexpected error in compare_with_deezer: {e}")
            QMessageBox.critical(self, "Comparison Error", f"An unexpected error occurred: {e}")
            # Reset UI state
            self.compare_btn.setEnabled(True)
            self.comparison_progress.setVisible(False)
    
    def fast_compare_with_deezer(self):
        if not self.config.get_deezer_arl():
            QMessageBox.warning(self, "No ARL Token", "Please set your Deezer ARL token in Settings.")
            return
        if not self.local_albums:
            QMessageBox.warning(self, "No Library Data", 
                              "No library scan data found. Please scan your library using the 'Scan Library' button above before running a comparison.")
            return
        
        # Filter albums to only include those from currently configured library paths
        # First try to get library paths from current config
        library_paths = self.config.get_library_paths()
        
        # If no current paths, try to get them from the scan results
        if not library_paths:
            scan_data = self.config.load_scan_results()
            if scan_data and scan_data.get('library_paths'):
                library_paths = scan_data['library_paths']
                logger.info(f"Using library paths from scan results: {library_paths}")
            else:
                logger.warning("No library paths configured and none found in scan results")
                QMessageBox.warning(self, "No Library Paths", 
                                  "No library paths configured. Please add library paths in the Library Paths section above, "
                                  "or re-scan your library to update the configuration.")
                return
        else:
            logger.info(f"Using configured library paths: {library_paths}")
            
        # Only include albums whose folder_path is within the configured library paths
        albums = []
        for album in self.local_albums:
            folder_path = album.get('folder_path', '')
            if folder_path:
                # Normalize paths for comparison (handle Windows path separators and case)
                folder_path_normalized = os.path.normpath(folder_path).lower()
                # Check if this album's folder is within any of the configured library paths
                for lib_path in library_paths:
                    lib_path_normalized = os.path.normpath(lib_path).lower()
                    if folder_path_normalized.startswith(lib_path_normalized):
                        albums.append(album)
                        break
        
        if not albums:
            QMessageBox.warning(self, "No Albums Found", 
                              "No albums found in the currently configured library paths. "
                              "Please check your library path configuration.")
            return
        
        # Exclude live albums if checkbox is checked
        if hasattr(self, 'exclude_live_checkbox') and self.exclude_live_checkbox.isChecked():
            albums = [a for a in albums if 'live' not in (a.get('album', '') or '').lower() and 'live' not in (a.get('album_artist', '') or '').lower()]
        # Debug output: log number of tracks, unique album_artists, and sample album_artist/album pairs
        from pathlib import Path
        log_path = Path(__file__).parent.parent / 'debug_fast_comparison_input.log'
        with open(log_path, 'w', encoding='utf-8') as log_file:
            log_file.write(f"=== LIBRARY PATH FILTERING DEBUG ===\n")
            log_file.write(f"Configured library paths: {library_paths}\n")
            log_file.write(f"Total albums before filtering: {len(self.local_albums)}\n")
            log_file.write(f"Albums after path filtering: {len(albums)}\n")
            
            # Show some examples of albums that were excluded
            excluded_albums = [a for a in self.local_albums if a not in albums]
            log_file.write(f"Albums excluded by path filtering: {len(excluded_albums)}\n")
            log_file.write(f"Sample excluded albums (up to 5):\n")
            for i, album in enumerate(excluded_albums[:5]):
                log_file.write(f"  EXCLUDED: {album.get('album_artist', 'Unknown')} - {album.get('album', 'Unknown')} | Path: {album.get('folder_path', 'No path')}\n")
            
            # Show some examples of filtered albums with their paths
            log_file.write(f"Sample included albums with paths (up to 10):\n")
            for i, album in enumerate(albums[:10]):
                log_file.write(f"  INCLUDED: {album.get('album_artist', 'Unknown')} - {album.get('album', 'Unknown')} | Path: {album.get('folder_path', 'No path')}\n")
            
            filtered_tracks = [t for t in albums if (t.get('album_artist') if isinstance(t, dict) else getattr(t, 'album_artist', None)) and ((t.get('album_artist') if isinstance(t, dict) else getattr(t, 'album_artist', None)) or '').strip().lower() != 'various artists']
            log_file.write(f"Total tracks (album_artist != 'Various Artists'): {len(filtered_tracks)}\n")
            album_artists = set()
            album_artist_album_pairs = set()
            for t in filtered_tracks:
                album_artist = t.get('album_artist') if isinstance(t, dict) else getattr(t, 'album_artist', None)
                album = t.get('album') if isinstance(t, dict) else getattr(t, 'album', None)
                if album_artist:
                    album_artists.add(album_artist)
                if album_artist and album:
                    album_artist_album_pairs.add((album_artist, album))
            log_file.write(f"Unique album_artists: {len(album_artists)}\n")
            log_file.write(f"Sample album_artist/album pairs (up to 20):\n")
            for pair in list(album_artist_album_pairs)[:20]:
                log_file.write(f"  {pair[0]} | {pair[1]}\n")
        # Only use filtered tracks for comparison
        tracks_for_comparison = [trackinfo_to_dict(t) if not isinstance(t, dict) else t for t in filtered_tracks]
        self.fast_compare_btn.setEnabled(False)
        self.comparison_progress.setVisible(True)
        self.comparison_progress.setValue(0)
        self.comparison_progress.setMaximum(100)
        self.comparison_status_label.setVisible(True)
        self.comparison_status_label.setText("Starting fast album comparison...")
        self.fast_comparison_worker = FastComparisonWorker(self.config, tracks_for_comparison)
        self.fast_comparison_worker.progress_updated.connect(self.update_fast_comparison_progress)
        self.fast_comparison_worker.comparison_completed.connect(self.on_fast_comparison_completed)
        self.fast_comparison_worker.error_occurred.connect(self.on_comparison_error)
        self.fast_comparison_worker.start()

    def update_fast_comparison(self):
        """Update fast album comparison for new/changed album_artists only."""
        if not self.config.get_deezer_arl():
            QMessageBox.warning(self, "No ARL Token", "Please set your Deezer ARL token in Settings.")
            return
        if not self.local_albums:
            QMessageBox.warning(self, "No Library Data", "Please scan your library first.")
            return
        # Debug output: log number of tracks, unique album_artists, and sample album_artist/album pairs
        from pathlib import Path
        log_path = Path(__file__).parent.parent / 'debug_fast_comparison_input.log'
        with open(log_path, 'w', encoding='utf-8') as log_file:
            filtered_tracks = [t for t in self.local_albums if (t.get('album_artist') if isinstance(t, dict) else getattr(t, 'album_artist', None)) and ((t.get('album_artist') if isinstance(t, dict) else getattr(t, 'album_artist', None)) or '').strip().lower() != 'various artists']
            log_file.write(f"Total tracks (album_artist != 'Various Artists'): {len(filtered_tracks)}\n")
            album_artists = set()
            album_artist_album_pairs = set()
            for t in filtered_tracks:
                album_artist = t.get('album_artist') if isinstance(t, dict) else getattr(t, 'album_artist', None)
                album = t.get('album') if isinstance(t, dict) else getattr(t, 'album', None)
                if album_artist:
                    album_artists.add(album_artist)
                if album_artist and album:
                    album_artist_album_pairs.add((album_artist, album))
            log_file.write(f"Unique album_artists: {len(album_artists)}\n")
            log_file.write(f"Sample album_artist/album pairs (up to 20):\n")
            for pair in list(album_artist_album_pairs)[:20]:
                log_file.write(f"  {pair[0]} | {pair[1]}\n")
        # Only use filtered tracks for comparison
        tracks_for_comparison = [trackinfo_to_dict(t) if not isinstance(t, dict) else t for t in filtered_tracks]
        # Load cached results
        cached_results = self.load_fast_comparison_results()
        if not cached_results:
            QMessageBox.information(self, "No Cached Results", 
                                  "No cached fast comparison results found. Please run a full fast comparison first.")
            return
        self.update_fast_comparison_btn.setEnabled(False)
        self.comparison_progress.setVisible(True)
        self.comparison_progress.setValue(0)
        self.comparison_progress.setMaximum(100)
        self.comparison_status_label.setVisible(True)
        self.comparison_status_label.setText("Starting incremental fast album comparison...")
        self.incremental_fast_comparison_worker = IncrementalFastComparisonWorker(
            self.config, tracks_for_comparison, cached_results
        )
        self.incremental_fast_comparison_worker.progress_updated.connect(self.update_fast_comparison_progress)
        self.incremental_fast_comparison_worker.comparison_completed.connect(self.on_fast_comparison_completed)
        self.incremental_fast_comparison_worker.error_occurred.connect(self.on_comparison_error)
        self.incremental_fast_comparison_worker.start()
    
    def reevaluate_with_new_settings(self):
        """Re-evaluate album matching using current threshold and normalization on cached data, with progress bar and status updates."""
        if not hasattr(self, 'fast_comparison_results') or not self.fast_comparison_results:
            QMessageBox.warning(self, "No Cached Results", "No cached fast album comparison results found. Please run a comparison first.")
            return
        from core.comparison_engine import ComparisonEngine
        engine = ComparisonEngine(None, self.config)  # type: ignore
        new_results = {
            'artists': {},
            'statistics': {
                'total_artists': 0,
                'total_local_albums': 0,
                'total_deezer_albums': 0,
                'total_missing_albums': 0
            }
        }
        artists = list(self.fast_comparison_results.get('artists', {}).items())
        total_artists = len(artists)
        self.reevaluate_btn.setEnabled(False)
        self.comparison_progress.setVisible(True)
        self.comparison_progress.setValue(0)
        self.comparison_progress.setMaximum(total_artists)
        self.comparison_status_label.setVisible(True)
        self.comparison_status_label.setText("Starting re-evaluation...")
        QApplication.processEvents()
        for idx, (artist, info) in enumerate(artists, 1):
            local_albums = set(info.get('local_albums', []))
            deezer_albums = set(info.get('deezer_albums', []))
            missing_albums = []
            matched_local_albums = set()
            for deezer_album in deezer_albums:
                best_match = None
                best_score = 0
                for local_album in local_albums:
                    if local_album in matched_local_albums:
                        continue
                    score = engine.fuzzy_match_albums(deezer_album, local_album)
                    if score > best_score and score >= engine.album_match_threshold:
                        best_score = score
                        best_match = local_album
                if best_match:
                    matched_local_albums.add(best_match)
                else:
                    missing_albums.append(deezer_album)
                # Update status for each album
                self.comparison_status_label.setText(f"Re-evaluating: {artist} - {deezer_album} ({idx}/{total_artists})")
                QApplication.processEvents()
            missing_albums.sort()
            new_results['artists'][artist] = {
                'deezer_id': info.get('deezer_id'),
                'deezer_name': info.get('deezer_name'),
                'local_albums': list(sorted(local_albums)),
                'deezer_albums': list(sorted(deezer_albums)),
                'missing_albums': missing_albums,
                'status': info.get('status', 'found')
            }
            new_results['statistics']['total_artists'] += 1
            new_results['statistics']['total_local_albums'] += len(local_albums)
            new_results['statistics']['total_deezer_albums'] += len(deezer_albums)
            new_results['statistics']['total_missing_albums'] += len(missing_albums)
            self.comparison_progress.setValue(idx)
            QApplication.processEvents()
        # Update UI with new results
        self.fast_comparison_results = new_results
        stats = new_results.get("statistics", {})
        summary = f"""
Fast Album Comparison Results (Re-evaluated):
=============================================

📊 Statistics:
- Artists analyzed: {stats.get('total_artists', 0)}
- Local albums: {stats.get('total_local_albums', 0)}
- Deezer albums: {stats.get('total_deezer_albums', 0)}
- Missing albums: {stats.get('total_missing_albums', 0)}
"""
        self.summary_text.setText(summary)
        if hasattr(self, 'artists_tree'):
            self.artists_tree.clear()
            for artist, info in new_results.get('artists', {}).items():
                missing_albums = info.get('missing_albums', [])
                if missing_albums:
                    item = QTreeWidgetItem([artist, f"{len(missing_albums)} albums"])
                    item.setCheckState(0, Qt.CheckState.Unchecked)
                    item.setData(0, Qt.ItemDataRole.UserRole, info)
                    self.artists_tree.addTopLevelItem(item)
        self.comparison_progress.setVisible(False)
        self.comparison_status_label.setVisible(False)
        self.reevaluate_btn.setEnabled(True)
        QMessageBox.information(self, "Re-evaluation Complete", "Album matching has been re-evaluated with the new settings.")
    
    def debug_reevaluate_with_new_settings(self):
        """Debug re-evaluation for a selected artist with detailed logging."""
        if not hasattr(self, 'fast_comparison_results') or not self.fast_comparison_results:
            QMessageBox.warning(self, "No Cached Results", "No cached fast album comparison results found. Please run a comparison first.")
            return
        from core.comparison_engine import ComparisonEngine
        engine = ComparisonEngine(None, self.config)  # type: ignore
        # Prompt for artist
        artist_list = list(self.fast_comparison_results.get('artists', {}).keys())
        artist, ok = QInputDialog.getItem(self, "Select Artist for Debug Scan", "Artist:", artist_list, 0, False)
        if not ok or not artist:
            return
        # Setup debug log
        log_path = Path(__file__).parent.parent / "debug_album_matching.log"
        log_file = open(log_path, 'w', encoding='utf-8')
        info = self.fast_comparison_results['artists'][artist]
        local_albums = set(info.get('local_albums', []))
        deezer_albums = set(info.get('deezer_albums', []))
        log_file.write(f"Debugging artist: {artist}\n")
        log_file.write(f"Local albums: {local_albums}\n")
        log_file.write(f"Deezer albums: {deezer_albums}\n\n")
        for deezer_album in deezer_albums:
            best_match = None
            best_score = 0
            best_debug = None
            for local_album in local_albums:
                score = engine.fuzzy_match_albums(deezer_album, local_album)
                norm_deezer = engine.normalize_album_title(deezer_album)
                norm_local = engine.normalize_album_title(local_album)
                debug_line = f"Deezer: '{deezer_album}' | Local: '{local_album}' | Norm Deezer: '{norm_deezer}' | Norm Local: '{norm_local}' | Score: {score}"
                if score > best_score and score >= engine.album_match_threshold:
                    best_score = score
                    best_match = local_album
                    best_debug = debug_line + " [MATCH]"
                else:
                    log_file.write(debug_line + "\n")
            if best_match:
                log_file.write(best_debug + "\n")
            else:
                log_file.write(f"No match for Deezer album: '{deezer_album}'\n")
        log_file.close()
        QMessageBox.information(self, "Debug Complete", f"Debug info written to {log_path}")
    
    def download_selected_items(self):
        """Download selected missing items."""
        if not hasattr(self, 'download_manager'):
            self.download_manager = DownloadManager(self.config.get_deemusic_path())
        
        if self.download_manager.get_queue_size() == 0:
            QMessageBox.warning(self, "Empty Queue", "No items in download queue.")
            return
        
        # Ensure the queue is written to download_queue_state.json before launching DeeMusic
        self.download_manager._save_state()
        # Launch DeeMusic with the queue
        if self.download_manager.launch_deemusic_with_queue():
            QMessageBox.information(self, "DeeMusic Launched",
                                  f"DeeMusic has been launched with {self.download_manager.get_queue_size()} tracks.\n\n"
                                  "The tracks will be downloaded to your configured music library.")
        else:
            # If launch fails, export to file instead
            export_file = self.download_manager.export_queue_to_deemusic()
            m3u_file = self.download_manager.create_m3u_playlist()
            
            QMessageBox.information(self, "Export Complete",
                                  f"Download queue exported to:\n"
                                  f"- JSON: {export_file}\n"
                                  f"- M3U: {m3u_file}\n\n"
                                  "You can import these files into DeeMusic manually.")
    
    def launch_deemusic(self):
        """Launch DeeMusic."""
        deemusic_path = self.deemusic_path_input.text().strip()
        if deemusic_path and Path(deemusic_path).exists():
            try:
                import subprocess
                subprocess.Popen([deemusic_path])
                self.status_bar.showMessage("DeeMusic launched")
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Could not launch DeeMusic: {e}")
        else:
            QMessageBox.warning(self, "Error", "Please set a valid DeeMusic path in Settings.")
    
    def browse_deemusic_path(self):
        """Browse for DeeMusic executable."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Select DeeMusic Executable", "", "Executable Files (*.exe)"
        )
        if path:
            self.deemusic_path_input.setText(path)
    
    def save_settings(self):
        """Save settings from the Settings tab."""
        self.config.set_deemusic_path(self.deemusic_path_input.text().strip())
        self.config.set_deezer_arl(self.arl_input.text().strip())
        # Save album match threshold
        if hasattr(self.config, 'set_album_match_threshold'):
            self.config.set_album_match_threshold(self.album_threshold_slider.value())
        QMessageBox.information(self, "Settings Saved", "Settings have been saved successfully.")
    
    def load_settings(self):
        """Load settings into the Settings tab."""
        self.deemusic_path_input.setText(self.config.get_deemusic_path())
        self.arl_input.setText(self.config.get_deezer_arl())
        # Load album match threshold
        if hasattr(self.config, 'get_album_match_threshold'):
            threshold = self.config.get_album_match_threshold()
            self.album_threshold_slider.setValue(threshold)
            self.album_threshold_label.setText(f"{threshold}%")
    
    def save_scan_results(self, albums: List[Dict]) -> None:
        """Save scan results to disk."""
        try:
            # Save album-level data directly
            albums_data = {
                'albums': albums,
                'scan_timestamp': datetime.now().isoformat()
            }
            
            # Save to config
            self.config.save_scan_results(albums_data)
            logger.info(f"Saved {len(albums)} albums to disk")
            
        except Exception as e:
            logger.error(f"Error saving scan results: {e}")
    
    def load_saved_scan_results(self) -> None:
        """Load previously saved scan results."""
        try:
            scan_data = self.config.load_scan_results()
            
            # Handle different scan result formats
            albums = None
            if scan_data:
                if scan_data.get('albums'):
                    # Library Scanner format
                    albums = scan_data['albums']
                    logger.info("Found Library Scanner format scan results")
                elif scan_data.get('files'):
                    # Main DeeMusic format - convert to album format
                    logger.info("Found main DeeMusic format scan results, converting to album format...")
                    albums = self._convert_files_to_albums(scan_data['files'])
                    logger.info(f"Converted {len(scan_data['files'])} files to {len(albums)} albums")
            
            # If no library paths are configured but scan results exist, auto-populate paths
            if albums:
                if not self.config.get_library_paths() and scan_data.get('library_paths'):
                    self.config.config['library_paths'] = scan_data['library_paths']
                    self.config.save_config()
                # Ensure albums is a list
                if not isinstance(albums, list):
                    logger.error(f"Albums is not a list: {type(albums)}")
                    albums = []
                logger.info(f"Found albums list with {len(albums)} entries (type: {type(albums)})")
                # Debug: log the type and content of the first 3 album entries
                # if isinstance(albums, list):
                #     for i, entry in enumerate(albums[:3]):
                #         logger.info(f"Album entry {i}: type={type(entry)}, value={entry}")
                # else:
                #     logger.error(f"'albums' is not a list, but {type(albums)}: {albums}")
                #     albums = []
                # Debug output: log number of albums, unique artists, and sample artist/album pairs
                from pathlib import Path
                log_path = Path(__file__).parent.parent / 'debug_scan_load.log'
                with open(log_path, 'w', encoding='utf-8') as log_file:
                    log_file.write(f"Total albums loaded: {len(albums)}\n")
                    artists = set()
                    artist_album_pairs = set()
                    for album in albums:
                        if not isinstance(album, dict):
                            logger.warning(f"Skipping non-dict album entry: {album}")
                            continue
                        artist = album.get('album_artist', '')
                        album_name = album.get('album', '')
                        if artist:
                            artists.add(artist)
                        if artist and album_name:
                            artist_album_pairs.add((artist, album_name))
                    log_file.write(f"Unique artists: {len(artists)}\n")
                    log_file.write(f"Sample artist/album pairs (up to 20):\n")
                    for pair in list(artist_album_pairs)[:20]:
                        log_file.write(f"  {str(pair[0])} | {str(pair[1])}\n")
                # Only keep valid dict albums
                albums = [a for a in albums if isinstance(a, dict)]
                self.local_albums = albums
                self.fast_compare_btn.setEnabled(True)
                self.clear_results_btn.setEnabled(True) if hasattr(self, 'clear_results_btn') else None
                self.update_scan_btn.setEnabled(True)
                # Update UI with loaded results
                artists = set(album['album_artist'] for album in albums)
                total_tracks = sum(album['num_tracks'] for album in albums)
                scan_timestamp = scan_data.get('scan_timestamp', '')
                try:
                    from datetime import datetime
                    timestamp = datetime.fromisoformat(scan_timestamp)
                    time_str = timestamp.strftime("%Y-%m-%d %H:%M")
                except:
                    time_str = "unknown time"
                stats_text = f"Loaded previous scan ({time_str}): {len(albums)} albums from {len(artists)} artists ({total_tracks} total tracks)"
                self.scan_status.setText(stats_text)
                logger.info(f"Loaded {len(albums)} albums from previous scan")
                # Load cached comparison results if available
                self.load_saved_comparison_results() if hasattr(self, 'load_saved_comparison_results') else None
                # Load cached fast comparison results if available
                self.load_saved_fast_comparison_results()
            else:
                # Show message if no scan results
                if hasattr(self, 'summary_text'):
                    self.summary_text.setText("No scan results found. Please scan your library.")
        except Exception as e:
            logger.error(f"Error loading saved scan results: {e}")
            if hasattr(self, 'summary_text'):
                self.summary_text.setText(f"Error loading scan results: {e}")
    
    def _convert_files_to_albums(self, files: List[Dict]) -> List[Dict]:
        """Convert file-based scan results to album-based format."""
        albums_dict = {}
        
        for file_info in files:
            if not isinstance(file_info, dict):
                continue
                
            album_artist = file_info.get('album_artist', '').strip()
            album_name = file_info.get('album', '').strip()
            
            if not album_artist or not album_name or album_artist.lower() == 'various artists':
                continue
                
            # Create album key
            album_key = f"{album_artist}|{album_name}"
            
            if album_key not in albums_dict:
                # Extract folder path from file path
                file_path = file_info.get('path', '')
                folder_path = str(Path(file_path).parent) if file_path else ''
                
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
            file_format = file_info.get('format', '')
            if file_format:
                album_info['file_formats'].add(file_format)
        
        # Convert sets to lists for JSON serialization
        albums = []
        for album_info in albums_dict.values():
            album_info['file_formats'] = list(album_info['file_formats'])
            albums.append(album_info)
        
        return albums
    
    def clear_scan_results(self) -> None:
        """Clear saved scan results."""
        try:
            self.config.clear_scan_results()
            self.local_albums = []
            self.compare_btn.setEnabled(False)
            self.fast_compare_btn.setEnabled(False)
            self.clear_results_btn.setEnabled(False)
            self.update_scan_btn.setEnabled(False)
            self.scan_status.setText("Scan results cleared - Ready to scan")
            logger.info("Scan results cleared")
        except Exception as e:
            logger.error(f"Error clearing scan results: {e}")
    
    def update_comparison_progress(self, status: str):
        """Update comparison progress status."""
        self.comparison_progress.setFormat(status)
        self.status_bar.showMessage(status)
    
    def update_fast_comparison_progress(self, artist, idx, total, album):
        percent = int((idx / total) * 100) if total else 0
        self.comparison_progress.setMaximum(total)
        self.comparison_progress.setValue(idx)
        if album:
            self.comparison_status_label.setText(f"Comparing: {artist} - {album} ({idx}/{total})")
        else:
            self.comparison_status_label.setText(f"Comparing: {artist} ({idx}/{total})")
    
    def get_library_hash(self):
        """Compute a hash of the current local library for cache validation."""
        # Use file_path, title, artist, album, track_number for hash
        items = [
            f"{a.get('file_path','')}|{a.get('title','')}|{a.get('artist','')}|{a.get('album','')}|{a.get('track_number','')}"
            if isinstance(a, dict) else
            f"{getattr(a,'file_path','')}|{getattr(a,'title','')}|{getattr(a,'artist','')}|{getattr(a,'album','')}|{getattr(a,'track_number','')}"
            for a in self.local_albums
        ]
        items.sort()
        m = hashlib.sha256()
        for item in items:
            m.update(item.encode('utf-8'))
        return m.hexdigest()

    def save_comparison_results(self, results):
        """Save comparison results to disk with timestamp and library hash."""
        data = {
            "timestamp": datetime.now().isoformat(),
            "library_hash": self.get_library_hash(),
            "results": results
        }
        cache_file = self.config.config_dir / "comparison_results.json"
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)

    def load_comparison_results(self):
        """Load comparison results from disk if library hash matches."""
        cache_file = self.config.config_dir / "comparison_results.json"
        if not cache_file.exists():
            return None
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if data.get('library_hash') == self.get_library_hash():
                return data.get('results')
        except Exception as e:
            logger.error(f"Error loading comparison results: {e}")
        return None

    def load_saved_comparison_results(self):
        """Load and display saved comparison results if available."""
        results = self.load_comparison_results()
        if results:
            self.comparison_results = results
            self.on_comparison_completed(results)
            logger.info("Loaded cached Deezer comparison results.")

    def save_fast_comparison_results(self, results):
        """Save fast album comparison results to disk."""
        library_hash = self.get_library_hash()
        self.config.save_fast_comparison_results(results, library_hash)

    def load_fast_comparison_results(self):
        """Load fast album comparison results from disk if library hash matches."""
        library_hash = self.get_library_hash()
        return self.config.load_fast_comparison_results(library_hash)

    def load_saved_fast_comparison_results(self):
        """Load and display saved fast comparison results if available."""
        results = self.load_fast_comparison_results()
        if results:
            # Store results and populate the hierarchical view
            self.fast_comparison_results = results
            
            # Clear both trees
            self.artists_tree.clear()
            self.albums_tree.clear()
            
            stats = results.get("statistics", {})
            summary = f"""
Fast Album Comparison Results (Cached):
=======================================

📊 Statistics:
- Artists analyzed: {stats.get('total_artists', 0)}
- Local albums: {stats.get('total_local_albums', 0)}
- Deezer albums: {stats.get('total_deezer_albums', 0)}
- Missing albums: {stats.get('total_missing_albums', 0)}
"""
            self.summary_text.setText(summary)
            
            # Populate artists tree
            for artist, info in results.get('artists', {}).items():
                missing_albums = info.get('missing_albums', [])
                if missing_albums:  # Only show artists with missing albums
                    item = QTreeWidgetItem([artist, f"{len(missing_albums)} albums"])
                    item.setCheckState(0, Qt.CheckState.Unchecked)
                    # Store reference to artist info for easy access
                    item.setData(0, Qt.ItemDataRole.UserRole, info)
                    self.artists_tree.addTopLevelItem(item)
            
            logger.info("Loaded cached fast album comparison results.")
            
            # Enable import to DeeMusic button if we have results
            if hasattr(self, 'import_to_deemusic_btn'):
                self.import_to_deemusic_btn.setEnabled(True)
            
            # Enable incremental update button
            if hasattr(self, 'update_fast_comparison_btn'):
                self.update_fast_comparison_btn.setEnabled(True)
        else:
            # Show message if no cached results
            if hasattr(self, 'summary_text'):
                self.summary_text.setText("No cached fast album comparison results found. Please run a comparison.")

    def on_comparison_completed(self, results: Dict[str, Any]):
        """Handle comparison completion."""
        self.save_comparison_results(results)
        self.compare_btn.setEnabled(True)
        self.fast_compare_btn.setEnabled(True)
        self.comparison_progress.setVisible(False)
        self.comparison_results = results
        
        # Clear existing results
        self.summary_text.clear()
        self.missing_tree.clear()
        self.missing_albums_tree.clear() # Clear missing albums tree
        
        # Update summary
        stats = results.get("statistics", {})
        summary = f"""
Comparison Results:
==================

📊 Statistics:
- Local albums analyzed: {stats.get('total_local_albums', 0)}
- Deezer albums found: {stats.get('total_deezer_albums', 0)}
- Matched albums: {stats.get('matched_count', 0)}
- Missing from local: {stats.get('missing_count', 0)}
- Not on Deezer: {stats.get('not_found_count', 0)}

🎤 Artists Analyzed:
"""
        
        # Add artist details
        for artist_name, artist_info in results.get("artists_analyzed", {}).items():
            if artist_info['status'] == 'found':
                summary += f"\n{artist_name}:"
                summary += f"\n  - Local albums: {artist_info['local_albums']}"
                summary += f"\n  - Deezer albums: {artist_info['deezer_albums']}"
                summary += f"\n  - Matched: {artist_info['matched']}"
                summary += f"\n  - Missing: {artist_info['missing']}"
            else:
                summary += f"\n{artist_name}: Not found on Deezer"
        
        self.summary_text.setText(summary)
        
        # Populate missing tracks tree
        missing_tracks = results.get("missing_from_local", [])
        for item in missing_tracks:
            track = item["deezer_track"]
            tree_item = QTreeWidgetItem([
                track.get("title", "Unknown"),
                item.get("artist", "Unknown"),
                item.get("album", "Unknown"),
                f"{track.get('duration', 0) // 60}:{track.get('duration', 0) % 60:02d}"
            ])
            tree_item.setData(0, Qt.ItemDataRole.UserRole, item)
            self.missing_tree.addTopLevelItem(tree_item)
        
        # Populate missing albums tree
        missing_albums = results.get("missing_albums", [])
        for artist, albums_info in missing_albums.items():
            for album_name in albums_info.get("missing_albums", []):
                item = QTreeWidgetItem([artist, album_name])
                self.missing_albums_tree.addTopLevelItem(item)
        
        # Enable action buttons if there are missing albums
        if missing_tracks:
            self.add_all_missing_btn.setEnabled(True)
            self.add_selected_btn.setEnabled(True)
            
        # Show completion message
        QMessageBox.information(self, "Comparison Complete",
                              f"Comparison completed successfully!\n\n"
                              f"Found {stats.get('missing_count', 0)} albums missing from your library.\n"
                              f"{stats.get('not_found_count', 0)} local albums not found on Deezer.")
        
        # Update status bar
        self.status_bar.showMessage(f"Comparison complete - {stats.get('missing_count', 0)} missing albums found")
    
    def on_comparison_error(self, error_message: str):
        """Handle comparison error."""
        self.compare_btn.setEnabled(True)
        self.fast_compare_btn.setEnabled(True) # Ensure fast compare is also enabled
        self.update_fast_comparison_btn.setEnabled(True) # Ensure incremental update is also enabled
        self.comparison_progress.setVisible(False)
        self.comparison_status_label.setVisible(False)
        
        QMessageBox.critical(self, "Comparison Error",
                           f"An error occurred during comparison:\n\n{error_message}")
        
        self.status_bar.showMessage("Comparison failed")
    
    def on_fast_comparison_completed(self, results: Dict[str, Any]):
        self.fast_compare_btn.setEnabled(True)
        self.comparison_progress.setVisible(False)
        self.comparison_status_label.setVisible(False)
        
        # Save fast comparison results
        self.save_fast_comparison_results(results)
        
        # Store results for use in hierarchical view
        self.fast_comparison_results = results
        
        # Clear both trees
        self.artists_tree.clear()
        self.albums_tree.clear()
        
        stats = results.get("statistics", {})
        summary = f"""
Fast Album Comparison Results:
=============================

📊 Statistics:
- Artists analyzed: {stats.get('total_artists', 0)}
- Local albums: {stats.get('total_local_albums', 0)}
- Deezer albums: {stats.get('total_deezer_albums', 0)}
- Missing albums: {stats.get('total_missing_albums', 0)}
"""
        self.summary_text.setText(summary)
        
        # Populate artists tree
        for artist, info in results.get('artists', {}).items():
            missing_albums = info.get('missing_albums', [])
            if missing_albums:  # Only show artists with missing albums
                item = QTreeWidgetItem([artist, f"{len(missing_albums)} albums"])
                item.setCheckState(0, Qt.CheckState.Unchecked)
                # Store reference to artist info for easy access
                item.setData(0, Qt.ItemDataRole.UserRole, info)
                self.artists_tree.addTopLevelItem(item)
        
        # Enable incremental update button
        self.update_fast_comparison_btn.setEnabled(True)
        
        # Enable import to DeeMusic button
        self.import_to_deemusic_btn.setEnabled(True)
        
        QMessageBox.information(self, "Fast Album Comparison Complete",
            f"Fast album comparison completed!\n\nMissing albums found: {stats.get('total_missing_albums', 0)}")

    def on_artist_selected(self, item, column):
        """Handle artist selection - show their albums in the right tree."""
        artist_name = item.text(0)
        self.load_albums_for_artist(artist_name)
    
    def on_artist_checkbox_changed(self, item, column):
        """Handle artist checkbox change - check/uncheck all their albums."""
        if column == 0:  # Only respond to checkbox column
            artist_name = item.text(0)
            check_state = item.checkState(0)
            self.update_albums_check_state(artist_name, check_state)
    
    def on_album_checkbox_changed(self, item, column):
        """Handle album checkbox change - update artist checkbox state."""
        if column == 0:  # Only respond to checkbox column
            self.update_artist_check_state()
    
    def load_albums_for_artist(self, artist_name):
        """Load albums for the selected artist into the albums tree."""
        self.albums_tree.clear()
        
        if not hasattr(self, 'fast_comparison_results'):
            return
        
        artist_info = self.fast_comparison_results.get('artists', {}).get(artist_name)
        if not artist_info:
            return
        
        missing_albums = artist_info.get('missing_albums', [])
        # Filter out live albums if the checkbox is checked
        if hasattr(self, 'exclude_live_checkbox') and self.exclude_live_checkbox.isChecked():
            missing_albums = [album for album in missing_albums if 'live' not in album.lower()]
        # Filter out alternate versions if the checkbox is checked
        if hasattr(self, 'exclude_alternate_checkbox') and self.exclude_alternate_checkbox.isChecked():
            # Use the same normalization as the comparison engine
            from core.comparison_engine import ComparisonEngine
            from services.deezer_service import DeezerService
            engine = ComparisonEngine(DeezerService(arl_token=None), self.config)
            local_albums = set(artist_info.get('local_albums', []))
            filtered_missing = []
            for missing_album in missing_albums:
                norm_missing = engine.normalize_album_title(missing_album)
                found = False
                for local_album in local_albums:
                    norm_local = engine.normalize_album_title(local_album)
                    # Consider a match if normalized titles are the same or fuzzy match >= threshold
                    if norm_missing == norm_local or engine.fuzzy_match(norm_missing, norm_local) >= engine.album_match_threshold:
                        found = True
                        break
                if not found:
                    filtered_missing.append(missing_album)
            missing_albums = filtered_missing
        for album in missing_albums:
            item = QTreeWidgetItem([album, artist_name])
            item.setCheckState(0, Qt.CheckState.Unchecked)
            # Store reference to artist for easy access
            item.setData(1, Qt.ItemDataRole.UserRole, artist_name)
            self.albums_tree.addTopLevelItem(item)
    
    def update_albums_check_state(self, artist_name, check_state):
        """Update all albums for an artist to match the artist's checkbox state."""
        for i in range(self.albums_tree.topLevelItemCount()):
            item = self.albums_tree.topLevelItem(i)
            if item.text(1) == artist_name:  # Check artist column
                item.setCheckState(0, check_state)
    
    def update_artist_check_state(self):
        """Update artist checkbox state based on album checkboxes."""
        # Get current artist from albums tree
        if self.albums_tree.topLevelItemCount() == 0:
            return
        
        first_album = self.albums_tree.topLevelItem(0)
        artist_name = first_album.text(1)
        
        # Count checked and unchecked albums for this artist
        checked_count = 0
        total_count = 0
        
        for i in range(self.albums_tree.topLevelItemCount()):
            item = self.albums_tree.topLevelItem(i)
            if item.text(1) == artist_name:
                total_count += 1
                if item.checkState(0) == Qt.CheckState.Checked:
                    checked_count += 1
        
        # Find the artist item in the artists tree
        for i in range(self.artists_tree.topLevelItemCount()):
            artist_item = self.artists_tree.topLevelItem(i)
            if artist_item.text(0) == artist_name:
                # Set checkbox state based on album states
                if checked_count == 0:
                    artist_item.setCheckState(0, Qt.CheckState.Unchecked)
                elif checked_count == total_count:
                    artist_item.setCheckState(0, Qt.CheckState.Checked)
                else:
                    artist_item.setCheckState(0, Qt.CheckState.PartiallyChecked)
                break
    
    def check_all_albums_for_artist(self):
        """Check all albums for the currently selected artist."""
        selected_items = self.artists_tree.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "No Selection", "Please select an artist first.")
            return
        
        artist_item = selected_items[0]
        artist_name = artist_item.text(0)
        
        # Check all albums for this artist
        for i in range(self.albums_tree.topLevelItemCount()):
            item = self.albums_tree.topLevelItem(i)
            if item.text(1) == artist_name:
                item.setCheckState(0, Qt.CheckState.Checked)
        
        # Update artist checkbox
        artist_item.setCheckState(0, Qt.CheckState.Checked)
    
    def check_all_albums(self):
        """Check all albums in the albums tree."""
        self.albums_tree.blockSignals(True)
        for i in range(self.albums_tree.topLevelItemCount()):
            item = self.albums_tree.topLevelItem(i)
            item.setCheckState(0, Qt.CheckState.Checked)
        self.albums_tree.blockSignals(False)
        # Update all artist checkboxes
        self.update_all_artist_check_states()
    
    def uncheck_all_items(self):
        """Uncheck all items in both trees."""
        # Uncheck all albums
        for i in range(self.albums_tree.topLevelItemCount()):
            item = self.albums_tree.topLevelItem(i)
            item.setCheckState(0, Qt.CheckState.Unchecked)
        
        # Uncheck all artists
        for i in range(self.artists_tree.topLevelItemCount()):
            item = self.artists_tree.topLevelItem(i)
            item.setCheckState(0, Qt.CheckState.Unchecked)
    
    def update_all_artist_check_states(self):
        """Update all artist checkbox states based on their albums."""
        # Group albums by artist
        artist_albums = {}
        for i in range(self.albums_tree.topLevelItemCount()):
            item = self.albums_tree.topLevelItem(i)
            artist = item.text(1)
            if artist not in artist_albums:
                artist_albums[artist] = {'checked': 0, 'total': 0}
            artist_albums[artist]['total'] += 1
            if item.checkState(0) == Qt.CheckState.Checked:
                artist_albums[artist]['checked'] += 1
        
        # Update artist checkboxes
        for i in range(self.artists_tree.topLevelItemCount()):
            artist_item = self.artists_tree.topLevelItem(i)
            artist_name = artist_item.text(0)
            
            if artist_name in artist_albums:
                checked = artist_albums[artist_name]['checked']
                total = artist_albums[artist_name]['total']
                
                if checked == 0:
                    artist_item.setCheckState(0, Qt.CheckState.Unchecked)
                elif checked == total:
                    artist_item.setCheckState(0, Qt.CheckState.Checked)
                else:
                    artist_item.setCheckState(0, Qt.CheckState.PartiallyChecked)

    def add_selected_albums_to_queue(self):
        """Fetch tracks for checked albums and add to download queue using a QThread worker."""
        # Get checked albums from the albums tree
        checked_albums = []
        for i in range(self.albums_tree.topLevelItemCount()):
            item = self.albums_tree.topLevelItem(i)
            if item.checkState(0) == Qt.CheckState.Checked:
                checked_albums.append({
                    'artist': item.text(1),
                    'album': item.text(0)
                })
        for i in range(self.artists_tree.topLevelItemCount()):
            artist_item = self.artists_tree.topLevelItem(i)
            if artist_item.checkState(0) == Qt.CheckState.Checked:
                artist_name = artist_item.text(0)
                artist_info = self.fast_comparison_results.get('artists', {}).get(artist_name, {})
                missing_albums = artist_info.get('missing_albums', [])
                for album in missing_albums:
                    if not any(a['artist'] == artist_name and a['album'] == album for a in checked_albums):
                        checked_albums.append({
                            'artist': artist_name,
                            'album': album
                        })
        if not checked_albums:
            QMessageBox.warning(self, "No Selection", "Please check albums or artists to add to queue.")
            return
        
        # CRITICAL FIX: Check queue size to prevent overload
        MAX_QUEUE_SIZE = 200  # Maximum albums to add at once
        if len(checked_albums) > MAX_QUEUE_SIZE:
            reply = QMessageBox.question(
                self, 
                "Large Queue Warning", 
                f"You're about to add {len(checked_albums)} albums to the queue.\n\n"
                f"Adding more than {MAX_QUEUE_SIZE} albums at once can cause DeeMusic to become unresponsive.\n\n"
                f"Would you like to:\n"
                f"• Continue with first {MAX_QUEUE_SIZE} albums (Recommended)\n"
                f"• Add all {len(checked_albums)} albums (May cause issues)\n"
                f"• Cancel",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
            )
            
            if reply == QMessageBox.StandardButton.Cancel:
                return
            elif reply == QMessageBox.StandardButton.Yes:
                checked_albums = checked_albums[:MAX_QUEUE_SIZE]
                QMessageBox.information(
                    self, 
                    "Queue Limited", 
                    f"Queue limited to first {MAX_QUEUE_SIZE} albums to prevent performance issues.\n\n"
                    f"You can add more albums after these complete."
                )
        
        arl_token = self.config.get_deezer_arl()
        if not arl_token:
            QMessageBox.warning(self, "No ARL Token", "Please set your Deezer ARL token in Settings.")
            return
        # Launch DeeMusic if not running (optional, implement is_deemusic_running if needed)
        if hasattr(self, 'launch_deemusic'):
            self.launch_deemusic()
        # Progress dialog
        self.progress_dialog = QProgressDialog("Fetching album tracklists from Deezer...", "Cancel", 0, len(checked_albums), self)
        self.progress_dialog.setWindowTitle("Adding Albums to Queue")
        self.progress_dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.progress_dialog.setMinimumDuration(0)
        self.progress_dialog.setValue(0)
        # Start worker
        self.add_albums_worker = AddAlbumsToQueueWorker(self.download_manager, checked_albums, arl_token)
        self.add_albums_worker.progress_updated.connect(self.progress_dialog.setValue)
        self.add_albums_worker.queue_completed.connect(self.on_add_albums_completed)
        self.add_albums_worker.error_occurred.connect(self.on_add_albums_error)
        self.add_albums_worker.debug_message.connect(self.on_add_albums_debug)
        self.progress_dialog.canceled.connect(self.add_albums_worker.terminate)
        self.add_albums_worker.start()

    def on_add_albums_completed(self, total_tracks, total_albums):
        self.progress_dialog.close()
        if total_tracks == 0:
            QMessageBox.information(self, "No Albums Added", "All tracks from the selected albums are already in the queue.")
            self.update_download_tab()
            return
        # After queueing, launch DeeMusic with the queue
        launched = False
        try:
            launched = self.download_manager.launch_deemusic_with_queue()
        except Exception as e:
            logging.exception("Error launching DeeMusic with queue:")
        if launched:
            QMessageBox.information(self, "Albums Added", f"Added {total_tracks} tracks from {total_albums} checked albums to the download queue. DeeMusic launched with the new queue.")
        else:
            QMessageBox.warning(self, "Albums Added", f"Added {total_tracks} tracks from {total_albums} checked albums to the download queue, but DeeMusic was not launched or no downloads were triggered. Please check DeeMusic and your queue.")
        self.update_download_tab()

    def on_add_albums_error(self, error_message):
        self.progress_dialog.close()
        logging.error(f"Error Adding Albums: {error_message}")
        QMessageBox.critical(self, "Error Adding Albums", f"An error occurred while adding albums to the queue:\n\n{error_message}")

    def on_add_albums_debug(self, message):
        logging.info(f"[AddAlbumsToQueueWorker] {message}")
    
    def add_all_missing_to_queue(self):
        """Add all missing tracks to download queue."""
        if not hasattr(self, 'download_manager'):
            self.download_manager = DownloadManager(self.config.get_deemusic_path())
        
        missing_tracks = self.comparison_results.get("missing_from_local", [])
        added_count = 0
        
        for item in missing_tracks:
            if self.download_manager.add_to_queue(item):
                added_count += 1
        
        QMessageBox.information(self, "Added to Queue",
                              f"Added {added_count} tracks to download queue.\n\n"
                              f"Total queue size: {self.download_manager.get_queue_size()}")
        
        self.update_download_tab()
    
    def add_selected_to_queue(self):
        """Add selected missing tracks to download queue."""
        if not hasattr(self, 'download_manager'):
            self.download_manager = DownloadManager(self.config.get_deemusic_path())
        
        selected_items = self.missing_tree.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "No Selection", "Please select tracks to add to queue.")
            return
        
        added_count = 0
        for tree_item in selected_items:
            track_data = tree_item.data(0, Qt.ItemDataRole.UserRole)
            if track_data and self.download_manager.add_to_queue(track_data):
                added_count += 1
        
        QMessageBox.information(self, "Added to Queue",
                              f"Added {added_count} tracks to download queue.\n\n"
                              f"Total queue size: {self.download_manager.get_queue_size()}")
        
        self.update_download_tab()
    
    def update_download_tab(self):
        """Update the download tab with current queue."""
        if not hasattr(self, 'download_manager'):
            return
        # Always reload the queue from disk to ensure UI is up to date
        self.download_manager._load_state()
        queue = self.download_manager.get_queue()
        stats = self.download_manager.get_download_stats()
        
        # Update download tab content
        content = f"""
Download Queue Status:
=====================

📊 Statistics:
- Queued: {stats['queued']}
- Completed: {stats['completed']}
- Failed: {stats['failed']}
- Total: {stats['total']}

📋 Current Queue:
"""
        
        if getattr(self, 'queue_album_view', True):
            # Album view: group by album, show one entry per album
            albums = self.download_manager.group_queue_by_album()
            for album_key, tracks in albums.items():
                artist, album = album_key.split('|')
                content += f"\n- {artist} — {album}  (Tracks: {len(tracks)})"
        else:
            # Track view: show every track
            for track in queue:
                content += f"\n- {track['artist']} — {track['album']} — {track['title']}"
        
        self.missing_items_text.setText(content)
        
        # Enable download button if queue has items
        self.download_selected_btn.setEnabled(stats['queued'] > 0)
    
    def refresh_download_queue(self):
        # Force reload of queue from disk and update UI
        if hasattr(self, 'download_manager'):
            self.download_manager._load_state()
        self.update_download_tab()
    
    def clear_comparison_cache(self):
        """Clear cached fast album comparison results only (not scan results)."""
        self.config.clear_fast_comparison_results()
        self.summary_text.clear()
        self.artists_tree.clear()
        self.albums_tree.clear()
        QMessageBox.information(self, "Cache Cleared", "Cached fast album comparison results have been cleared.")

    def closeEvent(self, event):
        """Handle the main window close event and ensure all worker threads are stopped."""
        # Stop any running workers
        for worker_name in [
            'scan_worker',
            'comparison_worker',
            'fast_comparison_worker',
            'incremental_fast_comparison_worker',
        ]:
            worker = getattr(self, worker_name, None)
            if worker and worker.isRunning():
                if hasattr(worker, 'cancel'):
                    worker.cancel()
                else:
                    worker.quit()
                worker.wait(2000)  # Wait up to 2 seconds for each to finish
        # Call any additional cleanup if needed (e.g., saving state)
        try:
            if hasattr(self, 'download_queue_widget') and self.download_queue_widget:
                self.download_queue_widget.save_queue_state()
        except Exception as e:
            print(f"Failed to save download queue state: {e}")
        # Call parent closeEvent to proceed with closing
        super().closeEvent(event)

    def on_exclude_live_albums_changed(self, state):
        # Refresh the albums tree for the currently selected artist
        selected_items = self.artists_tree.selectedItems()
        if selected_items:
            artist_name = selected_items[0].text(0)
            self.load_albums_for_artist(artist_name)
    
    def import_selected_to_deemusic(self):
        """Import selected albums to DeeMusic's download queue."""
        try:
            # Get selected albums from the UI
            selected_missing_albums = self.get_selected_missing_albums()
            
            if not selected_missing_albums:
                QMessageBox.information(
                    self, 
                    "No Selection", 
                    "Please select at least one album to import to DeeMusic.\n\n"
                    "Use the checkboxes in the Missing Albums view to select albums."
                )
                return
            
            # Open the import dialog
            dialog = QueueImportDialog(selected_missing_albums, self)
            dialog.exec()
            
        except Exception as e:
            logger.error(f"Error importing to DeeMusic: {e}")
            QMessageBox.critical(
                self, 
                "Import Error", 
                f"An error occurred while importing to DeeMusic:\n\n{str(e)}"
            )
    
    def get_selected_missing_albums(self):
        """Get the selected missing albums from the UI."""
        selected_albums = []
        
        try:
            # Check if we have fast comparison results
            if not hasattr(self, 'fast_comparison_results') or not self.fast_comparison_results:
                return selected_albums
            
            # Iterate through artists in the tree
            for i in range(self.artists_tree.topLevelItemCount()):
                artist_item = self.artists_tree.topLevelItem(i)
                artist_name = artist_item.text(0)
                
                # Get artist data from results
                artist_data = self.fast_comparison_results.get('artists', {}).get(artist_name, {})
                missing_albums = artist_data.get('missing_albums', [])
                
                # Check each missing album for this artist
                for missing_album in missing_albums:
                    # Find corresponding album item in the albums tree
                    for j in range(self.albums_tree.topLevelItemCount()):
                        album_item = self.albums_tree.topLevelItem(j)
                        
                        # Check if this album matches and is selected
                        if (album_item.text(0) == missing_album.deezer_album.title and
                            album_item.text(1) == missing_album.deezer_album.artist and
                            album_item.checkState(0) == Qt.CheckState.Checked):
                            
                            selected_albums.append(missing_album)
                            break
            
            logger.info(f"Found {len(selected_albums)} selected albums for import")
            return selected_albums
            
        except Exception as e:
            logger.error(f"Error getting selected albums: {e}")
            return []

 