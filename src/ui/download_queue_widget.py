"""
Widget to display the download queue.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QScrollArea, QFrame, QProgressBar,
    QPushButton, QHBoxLayout, QMessageBox, QDialog, QCheckBox
)
from PyQt6.QtCore import Qt
import logging
import json
from pathlib import Path

from .components.download_item_widget import DownloadItemWidget
# Import new group item widgets
from .components.download_group_item_widget import AlbumGroupItemWidget, PlaylistGroupItemWidget

logger = logging.getLogger(__name__)

class RetryOptionsDialog(QDialog):
    """Dialog to show retry options including proxy settings."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Retry Failed Downloads")
        self.setModal(True)
        self.resize(400, 200)
        
        layout = QVBoxLayout(self)
        
        # Description
        desc_label = QLabel(
            "Some downloads failed. Would you like to retry them with proxy enabled?\n\n"
            "This can help bypass geo-restrictions that may be causing failures."
        )
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)
        
        # Enable proxy checkbox
        self.enable_proxy_checkbox = QCheckBox("Enable proxy for retry")
        self.enable_proxy_checkbox.setChecked(False)
        layout.addWidget(self.enable_proxy_checkbox)
        
        # Proxy info label
        self.proxy_info_label = QLabel("Configure proxy settings in File > Settings > Network tab first.")
        self.proxy_info_label.setStyleSheet("color: #666; font-size: 11px;")
        self.proxy_info_label.setWordWrap(True)
        layout.addWidget(self.proxy_info_label)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.retry_button = QPushButton("Retry Downloads")
        self.retry_button.setDefault(True)
        self.retry_button.clicked.connect(self.accept)
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        
        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.retry_button)
        layout.addLayout(button_layout)
        
        # Check current proxy status
        self._update_proxy_info()
    
    def _update_proxy_info(self):
        """Update proxy info based on current configuration."""
        try:
            from config_manager import ConfigManager
            config = ConfigManager()
            proxy_config = config.get_setting("network.proxy", {})
            
            if proxy_config.get('enabled', False):
                host = proxy_config.get('host', '')
                port = proxy_config.get('port', '')
                proxy_type = proxy_config.get('type', 'http')
                
                if host and port:
                    self.proxy_info_label.setText(f"Current proxy: {proxy_type}://{host}:{port}")
                    self.enable_proxy_checkbox.setChecked(True)
                else:
                    self.proxy_info_label.setText("Proxy enabled but host/port not configured. Check Settings.")
            else:
                self.proxy_info_label.setText("Proxy not enabled. Configure in File > Settings > Network tab.")
        except Exception:
            self.proxy_info_label.setText("Configure proxy settings in File > Settings > Network tab first.")
    
    def should_use_proxy(self):
        """Return whether proxy should be used for retry."""
        return self.enable_proxy_checkbox.isChecked()

class DownloadQueueWidget(QWidget):
    """
    A widget that displays the list of current and pending downloads.
    """
    def __init__(self, download_manager=None, parent=None):
        super().__init__(parent)
        self.download_manager = download_manager
        # self.active_items = {} # OLD: To store DownloadItemWidget instances by item_id (str)
        
        # New storage for different item types
        self.active_album_groups = {} # album_id_str: AlbumGroupItemWidget
        self.active_playlist_groups = {} # playlist_id_str: PlaylistGroupItemWidget
        self.active_individual_tracks = {} # track_id_str: DownloadItemWidget
        self.track_to_group_map = {} # track_id_str: {'type': 'album'/'playlist', 'group_id': str}
        
        self.setObjectName("DownloadQueueWidget")
        self._setup_ui()
        if self.download_manager:
            self._connect_signals()

    def set_download_manager(self, download_manager):
        """Sets the download manager and connects signals if not already set."""
        if not self.download_manager and download_manager:
            self.download_manager = download_manager
            self._connect_signals()
        elif self.download_manager and download_manager and self.download_manager != download_manager:
            logger.warning("[DownloadQueueWidget] Attempting to change DownloadManager.")
            self.download_manager = download_manager
            self._connect_signals() 

    def _connect_signals(self):
        """Connects to signals from the DownloadManager."""
        if not self.download_manager or not hasattr(self.download_manager, 'signals'):
            logger.warning("[DownloadQueueWidget] Cannot connect signals, DownloadManager or its signals attribute is None.")
            return
        
        try:
            self.download_manager.signals.download_started.connect(self.add_download_item)
            self.download_manager.signals.download_progress.connect(self.update_download_progress)
            self.download_manager.signals.download_finished.connect(self._handle_download_finished)
            self.download_manager.signals.download_failed.connect(self._handle_download_failed)
            self.download_manager.signals.group_download_enqueued.connect(self._handle_group_download_enqueued)
            logger.info("[DownloadQueueWidget] Connected to DownloadManager signals.")
        except AttributeError as e:
            logger.error(f"[DownloadQueueWidget] Error connecting signals: {e}. DM might not have expected signals.")
        except Exception as e:
            logger.error(f"[DownloadQueueWidget] Unexpected error connecting signals: {e}", exc_info=True)

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 10, 5, 5)
        main_layout.setSpacing(5)

        title_label = QLabel("Download Queue")
        title_label.setObjectName("DownloadQueueTitle")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title_label)

        action_buttons_layout = QHBoxLayout()
        action_buttons_layout.setSpacing(5)
        self.clear_queue_button = QPushButton("Clear All") # Renamed for clarity
        self.clear_queue_button.setObjectName("ClearQueueButton")
        self.clear_queue_button.clicked.connect(self._handle_clear_all_clicked)
        action_buttons_layout.addWidget(self.clear_queue_button)
        self.clear_completed_button = QPushButton("Clear Completed")
        self.clear_completed_button.setObjectName("ClearCompletedButton")
        self.clear_completed_button.clicked.connect(self._handle_clear_completed_clicked)
        action_buttons_layout.addWidget(self.clear_completed_button)
        self.retry_failed_button = QPushButton("Retry Failed")
        self.retry_failed_button.setObjectName("RetryFailedButton")
        self.retry_failed_button.clicked.connect(self._handle_retry_failed_clicked)
        action_buttons_layout.addWidget(self.retry_failed_button)
        main_layout.addLayout(action_buttons_layout)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setObjectName("DownloadQueueScrollArea")
        self.scroll_content_widget = QWidget()
        self.scroll_content_widget.setObjectName("DownloadQueueScrollContent")
        self.items_layout = QVBoxLayout(self.scroll_content_widget)
        self.items_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.items_layout.setSpacing(3)
        self.scroll_area.setWidget(self.scroll_content_widget)
        main_layout.addWidget(self.scroll_area, 1)

    def add_download_item(self, item_data: dict):
        track_id_str = str(item_data.get('id'))
        item_title = item_data.get('title', 'Unknown Title')
        artist_name = item_data.get('artist', 'Unknown Artist')
        album_name = item_data.get('album', 'Unknown Album') # Album name for the track
        # item_type = item_data.get('type', 'track') # Type of the item this track belongs to (track, album_track, playlist_track)

        album_id_from_data = item_data.get('album_id')
        album_total_tracks = item_data.get('album_total_tracks')
        playlist_id_from_data = item_data.get('playlist_id')
        playlist_total_tracks = item_data.get('playlist_total_tracks')

        if not track_id_str:
            logger.error("[DownloadQueueWidget] add_download_item called with no track_id.")
            return

        # Check if this track_id is already part of a group or individual download
        if track_id_str in self.track_to_group_map or track_id_str in self.active_individual_tracks:
            logger.warning(f"[DownloadQueueWidget] Track {track_id_str} ('{item_title}') already processed. Duplicate start signal?")
            return

        logger.info(f"[DownloadQueueWidget] Processing download_started for track: {track_id_str} ('{item_title}'), AlbumID: {album_id_from_data}, PlaylistID: {playlist_id_from_data}")

        if album_id_from_data is not None and album_total_tracks is not None:
            album_id_str = str(album_id_from_data)
            if album_id_str not in self.active_album_groups:
                logger.info(f"Creating new AlbumGroupItemWidget for album_id: {album_id_str}, title: '{album_name}', total: {album_total_tracks}")
                group_widget = AlbumGroupItemWidget(
                    album_id=album_id_str, 
                    album_title=album_name, 
                    artist_name=artist_name, 
                    total_tracks=album_total_tracks
                )
                self.items_layout.addWidget(group_widget)
                self.active_album_groups[album_id_str] = group_widget
            else:
                group_widget = self.active_album_groups[album_id_str]
            
            group_widget.add_track(track_id_str, item_title)
            self.track_to_group_map[track_id_str] = {'type': 'album', 'group_id': album_id_str}

        elif playlist_id_from_data is not None and playlist_total_tracks is not None:
            playlist_id_str = str(playlist_id_from_data)
            # Playlist title might be in item_data directly or need fetching based on playlist_id if not.
            # For now, assume playlist_title is available or use a placeholder.
            playlist_title_for_group = item_data.get('playlist_title') or f"Playlist {playlist_id_str}" 
            if playlist_id_str not in self.active_playlist_groups:
                logger.info(f"Creating new PlaylistGroupItemWidget for playlist_id: {playlist_id_str}, title: '{playlist_title_for_group}', total: {playlist_total_tracks}")
                group_widget = PlaylistGroupItemWidget(
                    playlist_id=playlist_id_str,
                    playlist_title=playlist_title_for_group, 
                    total_tracks=playlist_total_tracks
                )
                
                # Connect group retry signal
                group_widget.retry_failed_tracks.connect(self._handle_group_retry)
                
                self.items_layout.addWidget(group_widget)
                self.active_playlist_groups[playlist_id_str] = group_widget
            else:
                group_widget = self.active_playlist_groups[playlist_id_str]

            group_widget.add_track(track_id_str, item_title)
            self.track_to_group_map[track_id_str] = {'type': 'playlist', 'group_id': playlist_id_str}

        else: # Individual track
            logger.info(f"[DownloadQueueWidget] Adding individual track download item: {track_id_str} ('{item_title}')")
            track_widget = DownloadItemWidget(
                item_id=track_id_str,
                item_title=item_title,
                artist_name=artist_name,
                album_name=album_name, # Pass album name for individual track display
                item_type='track' # Explicitly 'track' for individual items
            )
            
            # Connect retry signal
            track_widget.retry_requested.connect(self._handle_individual_retry)
            
            self.items_layout.addWidget(track_widget)
            self.active_individual_tracks[track_id_str] = track_widget

    def update_download_progress(self, track_id_str: str, progress_percentage: int):
        if track_id_str in self.track_to_group_map:
            group_info = self.track_to_group_map[track_id_str]
            group_type = group_info['type']
            group_id = group_info['group_id']
            if group_type == 'album' and group_id in self.active_album_groups:
                self.active_album_groups[group_id].update_track_progress(track_id_str, progress_percentage)
            elif group_type == 'playlist' and group_id in self.active_playlist_groups:
                self.active_playlist_groups[group_id].update_track_progress(track_id_str, progress_percentage)
        elif track_id_str in self.active_individual_tracks:
            self.active_individual_tracks[track_id_str].set_progress(progress_percentage)
        else:
            logger.warning(f"[DownloadQueueWidget] Progress for unknown/unmapped track_id: {track_id_str}")

    def _handle_download_finished(self, track_id_str: str):
        logger.info(f"[DownloadQueueWidget] Download finished for track: {track_id_str}")
        if track_id_str in self.track_to_group_map:
            group_info = self.track_to_group_map[track_id_str]
            group_type = group_info['type']
            group_id = group_info['group_id']
            if group_type == 'album' and group_id in self.active_album_groups:
                self.active_album_groups[group_id].handle_track_finished(track_id_str)
            elif group_type == 'playlist' and group_id in self.active_playlist_groups:
                self.active_playlist_groups[group_id].handle_track_finished(track_id_str)
        elif track_id_str in self.active_individual_tracks:
            widget = self.active_individual_tracks[track_id_str]
            widget.set_progress(100)
            widget.progress_bar.setFormat("Completed")
            widget.status = "completed"
        else:
            logger.warning(f"[DownloadQueueWidget] Finished signal for unknown/unmapped track_id: {track_id_str}")

    def _handle_download_failed(self, track_id_str: str, error_message: str):
        logger.error(f"[DownloadQueueWidget] Download failed for track {track_id_str}: {error_message}")
        if track_id_str in self.track_to_group_map:
            group_info = self.track_to_group_map[track_id_str]
            group_type = group_info['type']
            group_id = group_info['group_id']
            if group_type == 'album' and group_id in self.active_album_groups:
                self.active_album_groups[group_id].handle_track_failed(track_id_str, error_message)
            elif group_type == 'playlist' and group_id in self.active_playlist_groups:
                self.active_playlist_groups[group_id].handle_track_failed(track_id_str, error_message)
        elif track_id_str in self.active_individual_tracks:
            widget = self.active_individual_tracks[track_id_str]
            widget.set_failed(error_message)
        else:
            logger.warning(f"[DownloadQueueWidget] Failed signal for unknown/unmapped track_id: {track_id_str}")

    def _remove_widget_from_layout(self, widget_to_remove):
        if widget_to_remove:
            self.items_layout.removeWidget(widget_to_remove)
            widget_to_remove.deleteLater()

    def _handle_clear_all_clicked(self):
        logger.info("[DownloadQueueWidget] 'Clear All' clicked.")
        # Clear individual tracks
        for track_id in list(self.active_individual_tracks.keys()):
            widget = self.active_individual_tracks.pop(track_id)
            self._remove_widget_from_layout(widget)
            # Optionally, tell DownloadManager to cancel if it's an ongoing individual track
            if self.download_manager and widget.status not in ["completed", "failed"]:
                try: self.download_manager.cancel_download(int(track_id)) # Assuming track_id is numeric
                except: pass # Ignore errors during cancel call for cleanup

        # Clear album groups
        for album_id in list(self.active_album_groups.keys()):
            group_widget = self.active_album_groups.pop(album_id)
            # Optionally, tell DownloadManager to cancel all tracks in this group
            # This needs more sophisticated logic in DownloadManager or group widget
            for track_id_in_group in group_widget.get_managed_track_ids():
                 if track_id_in_group in self.track_to_group_map: del self.track_to_group_map[track_id_in_group]
                 # DM cancel for each track in group
                 if self.download_manager: 
                     try: self.download_manager.cancel_download(int(track_id_in_group))
                     except: pass
            self._remove_widget_from_layout(group_widget)

        # Clear playlist groups
        for playlist_id in list(self.active_playlist_groups.keys()):
            group_widget = self.active_playlist_groups.pop(playlist_id)
            for track_id_in_group in group_widget.get_managed_track_ids():
                 if track_id_in_group in self.track_to_group_map: del self.track_to_group_map[track_id_in_group]
                 if self.download_manager: 
                     try: self.download_manager.cancel_download(int(track_id_in_group))
                     except: pass
            self._remove_widget_from_layout(group_widget)
        
        self.track_to_group_map.clear()

    def _handle_clear_completed_clicked(self):
        logger.info("[DownloadQueueWidget] 'Clear Completed' clicked.")
        # For individual tracks
        for track_id in list(self.active_individual_tracks.keys()):
            widget = self.active_individual_tracks[track_id]
            if hasattr(widget, 'status') and widget.status == "completed":
                self._remove_widget_from_layout(self.active_individual_tracks.pop(track_id))

        # For album groups - remove group if ALL its tracks are completed or failed
        for album_id in list(self.active_album_groups.keys()):
            group_widget = self.active_album_groups[album_id]
            if group_widget.overall_status == "Completed" or \
               (group_widget.overall_status == "Completed with errors" and 
                group_widget.completed_tracks_count + group_widget.failed_tracks_count == group_widget.total_tracks):
                for track_id_in_group in group_widget.get_managed_track_ids():
                    if track_id_in_group in self.track_to_group_map: del self.track_to_group_map[track_id_in_group]
                self._remove_widget_from_layout(self.active_album_groups.pop(album_id))

        # For playlist groups - similar logic
        for playlist_id in list(self.active_playlist_groups.keys()):
            group_widget = self.active_playlist_groups[playlist_id]
            if group_widget.overall_status == "Completed" or \
               (group_widget.overall_status == "Completed with errors" and 
                group_widget.completed_tracks_count + group_widget.failed_tracks_count == group_widget.total_tracks):
                for track_id_in_group in group_widget.get_managed_track_ids():
                    if track_id_in_group in self.track_to_group_map: del self.track_to_group_map[track_id_in_group]
                self._remove_widget_from_layout(self.active_playlist_groups.pop(playlist_id))

    def _handle_retry_failed_clicked(self):
        logger.info("[DownloadQueueWidget] 'Retry Failed' clicked.")
        items_to_retry_individually = []
        groups_with_failed_tracks = []

        # Collect failed individual tracks
        for track_id, widget in self.active_individual_tracks.items():
            if hasattr(widget, 'status') and widget.status == "failed":
                items_to_retry_individually.append({
                    'id': widget.item_id, 'type': 'track', 
                    'title': widget.item_title, 'widget_instance': widget
                })
        
        # Collect failed tracks within album groups
        for album_id, group_widget in self.active_album_groups.items():
            failed_track_ids = group_widget.get_failed_track_ids()
            if failed_track_ids:
                groups_with_failed_tracks.append({
                    'type': 'album',
                    'group_id': album_id,
                    'group_widget': group_widget,
                    'failed_track_ids': failed_track_ids
                })
        
        # Collect failed tracks within playlist groups
        for playlist_id, group_widget in self.active_playlist_groups.items():
            failed_track_ids = group_widget.get_failed_track_ids()
            if failed_track_ids:
                groups_with_failed_tracks.append({
                    'type': 'playlist',
                    'group_id': playlist_id,
                    'group_widget': group_widget,
                    'failed_track_ids': failed_track_ids
                })

        if not items_to_retry_individually and not groups_with_failed_tracks:
            logger.info("[DownloadQueueWidget] No failed items to retry.")
            QMessageBox.information(self, "No Failed Downloads", "There are no failed downloads to retry.")
            return

        if not self.download_manager:
            logger.error("[DownloadQueueWidget] DownloadManager not available.")
            return

        # Show retry options dialog
        retry_dialog = RetryOptionsDialog(self)
        if retry_dialog.exec() != QDialog.DialogCode.Accepted:
            return  # User cancelled
            
        use_proxy = retry_dialog.should_use_proxy()
        
        # Temporarily enable proxy if requested
        original_proxy_state = None
        if use_proxy:
            try:
                from config_manager import ConfigManager
                config = ConfigManager()
                original_proxy_state = config.get_setting("network.proxy", {})
                
                # Enable proxy temporarily
                temp_proxy_config = original_proxy_state.copy()
                temp_proxy_config['enabled'] = True
                config.set_setting("network.proxy", temp_proxy_config)
                logger.info("Temporarily enabled proxy for retry downloads")
            except Exception as e:
                logger.error(f"Failed to enable proxy: {e}")
                QMessageBox.warning(self, "Proxy Error", f"Failed to enable proxy: {e}")

        try:
            # Retry individual failed tracks
            for item_info in items_to_retry_individually:
                track_id_str = item_info['id']
                widget = item_info['widget_instance']
                logger.info(f"Retrying individual track: {track_id_str}, Title: {item_info['title']}")
                widget.setStyleSheet("") 
                widget.progress_bar.setValue(0)
                widget.progress_bar.setFormat("Pending...")
                widget.status = "pending"
                widget.error_button.hide()
                widget.retry_button.hide()
                try:
                    numeric_item_id = int(track_id_str)
                    self.download_manager.download_track(numeric_item_id) 
                except Exception as e:
                    logger.error(f"Error retrying track {track_id_str}: {e}")
                    widget.status = "failed"
                    widget.progress_bar.setFormat("Error: Retry failed")

            # Retry failed tracks within groups
            for group_info in groups_with_failed_tracks:
                group_id = group_info['group_id']
                group_widget = group_info['group_widget']
                failed_track_ids = group_info['failed_track_ids']
                
                logger.info(f"Retrying {len(failed_track_ids)} failed tracks in {group_info['type']} group: {group_id}")
                
                # Use the existing group retry handler
                self._handle_group_retry(group_id, failed_track_ids)

        finally:
            # Restore original proxy state if it was temporarily changed
            if use_proxy and original_proxy_state is not None:
                try:
                    config.set_setting("network.proxy", original_proxy_state)
                    logger.info("Restored original proxy configuration")
                except Exception as e:
                    logger.error(f"Failed to restore proxy configuration: {e}")

    def _handle_group_download_enqueued(self, group_data: dict):
        if group_data is None:
            logger.error("[DownloadQueueWidget] Received None for group_data in _handle_group_download_enqueued. Aborting handling.")
            return

        group_id = group_data.get('group_id')
        group_title = group_data.get('group_title', 'Unknown Group')
        item_type = group_data.get('item_type') # 'album' or 'playlist'
        total_tracks = group_data.get('total_tracks', 0)
        artist_name_from_signal = group_data.get('artist_name') # Now available for albums
        # cover_url = group_data.get('cover_url') # TODO: Use cover_url

        if not group_id or not item_type:
            logger.error(f"[DownloadQueueWidget] Invalid group_download_enqueued signal data: {group_data}")
            return

        logger.info(f"[DownloadQueueWidget] Group download enqueued: Type='{item_type}', ID='{group_id}', Title='{group_title}', Artist='{artist_name_from_signal}', TotalTracks={total_tracks}")

        if item_type == 'album':
            if group_id not in self.active_album_groups:
                album_group_widget = AlbumGroupItemWidget(
                    album_id=group_id,
                    album_title=group_title,
                    artist_name=artist_name_from_signal,
                    total_tracks=total_tracks
                )
                
                # Connect group retry signal
                album_group_widget.retry_failed_tracks.connect(self._handle_group_retry)
                
                self.items_layout.addWidget(album_group_widget)
                self.active_album_groups[group_id] = album_group_widget
            else:
                logger.info(f"[DownloadQueueWidget] Album group {group_id} already exists, skipping widget creation.")
        elif item_type == 'playlist':
            if group_id not in self.active_playlist_groups:
                playlist_group_widget = PlaylistGroupItemWidget(
                    playlist_id=group_id,
                    playlist_title=group_title,
                    total_tracks=total_tracks
                )
                
                # Connect group retry signal
                playlist_group_widget.retry_failed_tracks.connect(self._handle_group_retry)
                
                self.items_layout.addWidget(playlist_group_widget)
                self.active_playlist_groups[group_id] = playlist_group_widget
            else:
                logger.info(f"[DownloadQueueWidget] Playlist group {group_id} already exists, skipping widget creation.")
        else:
            logger.warning(f"[DownloadQueueWidget] Unknown item_type '{item_type}' in group_download_enqueued signal.")

    def save_queue_state(self):
        """Saves the current state of the download queue to a file."""
        try:
            queue_state = {
                'failed_downloads': [],
                'completed_downloads': []
            }
            
            # Save failed individual tracks
            for track_id, widget in self.active_individual_tracks.items():
                if hasattr(widget, 'status') and widget.status == 'failed':
                    queue_state['failed_downloads'].append({
                        'track_id': track_id,
                        'title': widget.item_title,
                        'artist': widget.artist_name,
                        'album': widget.album_name,
                        'type': 'individual_track',
                        'error_message': getattr(widget, 'error_message', 'Unknown error')
                    })
                elif hasattr(widget, 'status') and widget.status == 'completed':
                    queue_state['completed_downloads'].append({
                        'track_id': track_id,
                        'title': widget.item_title,
                        'artist': widget.artist_name,
                        'album': widget.album_name,
                        'type': 'individual_track'
                    })
            
            # Save failed album groups
            for album_id, group in self.active_album_groups.items():
                failed_tracks = []
                completed_tracks = []
                for track_id, track_info in group.tracks.items():
                    if track_info.get('status') == 'failed':
                        failed_tracks.append({
                            'track_id': track_id,
                            'title': track_info.get('title', 'Unknown'),
                            'error_message': track_info.get('error_message', 'Unknown error')
                        })
                    elif track_info.get('status') == 'completed':
                        completed_tracks.append({
                            'track_id': track_id,
                            'title': track_info.get('title', 'Unknown')
                        })
                
                if failed_tracks:
                    queue_state['failed_downloads'].append({
                        'album_id': album_id,
                        'album_title': group.album_title,
                        'artist_name': group.artist_name,
                        'type': 'album',
                        'failed_tracks': failed_tracks
                    })
                
                if completed_tracks:
                    queue_state['completed_downloads'].append({
                        'album_id': album_id,
                        'album_title': group.album_title,
                        'artist_name': group.artist_name,
                        'type': 'album',
                        'completed_tracks': completed_tracks
                    })
            
            # Save failed playlist groups
            for playlist_id, group in self.active_playlist_groups.items():
                failed_tracks = []
                completed_tracks = []
                for track_id, track_info in group.tracks.items():
                    if track_info.get('status') == 'failed':
                        failed_tracks.append({
                            'track_id': track_id,
                            'title': track_info.get('title', 'Unknown'),
                            'error_message': track_info.get('error_message', 'Unknown error')
                        })
                    elif track_info.get('status') == 'completed':
                        completed_tracks.append({
                            'track_id': track_id,
                            'title': track_info.get('title', 'Unknown')
                        })
                
                if failed_tracks:
                    queue_state['failed_downloads'].append({
                        'playlist_id': playlist_id,
                        'playlist_title': group.playlist_title,
                        'type': 'playlist',
                        'failed_tracks': failed_tracks
                    })
                
                if completed_tracks:
                    queue_state['completed_downloads'].append({
                        'playlist_id': playlist_id,
                        'playlist_title': group.playlist_title,
                        'type': 'playlist',
                        'completed_tracks': completed_tracks
                    })
            
            file_path = Path('download_queue_state.json')
            with open(file_path, 'w') as f:
                json.dump(queue_state, f, indent=2)
            
            logger.debug(f"[DownloadQueueWidget] Queue state saved: {len(queue_state['failed_downloads'])} failed, {len(queue_state['completed_downloads'])} completed")
            
        except Exception as e:
            logger.error(f"[DownloadQueueWidget] Failed to save queue state: {e}")

    def load_queue_state(self):
        """Loads failed downloads from previous session and displays them."""
        try:
            file_path = Path('download_queue_state.json')
            if not file_path.exists():
                logger.debug("[DownloadQueueWidget] No previous queue state file found")
                return
                
            with open(file_path, 'r') as f:
                queue_state = json.load(f)
            
            failed_downloads = queue_state.get('failed_downloads', [])
            
            if failed_downloads:
                # Add a separator label
                separator_label = QLabel("Previous Session Failed Downloads")
                separator_label.setObjectName("DownloadQueueSeparator")
                separator_label.setStyleSheet("color: #ff6b6b; font-weight: bold; margin: 10px 0;")
                self.items_layout.addWidget(separator_label)
                
                # Recreate failed download items
                for failed_item in failed_downloads:
                    if failed_item['type'] == 'individual_track':
                        widget = DownloadItemWidget(
                            item_id=failed_item['track_id'],
                            item_title=failed_item['title'],
                            artist_name=failed_item['artist'],
                            album_name=failed_item['album'],
                            item_type='track'
                        )
                        
                        # Connect retry signal
                        widget.retry_requested.connect(self._handle_individual_retry)
                        
                        widget.set_failed(failed_item.get('error_message', 'Unknown error'))
                        self.items_layout.addWidget(widget)
                        self.active_individual_tracks[failed_item['track_id']] = widget
                        
                    elif failed_item['type'] == 'album':
                        group_widget = AlbumGroupItemWidget(
                            album_id=failed_item['album_id'],
                            album_title=failed_item['album_title'],
                            artist_name=failed_item['artist_name'],
                            total_tracks=len(failed_item['failed_tracks'])
                        )
                        
                        # Connect group retry signal
                        group_widget.retry_failed_tracks.connect(self._handle_group_retry)
                        
                        for track in failed_item['failed_tracks']:
                            group_widget.add_track(track['track_id'], track['title'])
                            group_widget.handle_track_failed(track['track_id'], track.get('error_message', 'Unknown error'))
                            # Add to track mapping for proper signal routing
                            self.track_to_group_map[track['track_id']] = {'type': 'album', 'group_id': failed_item['album_id']}
                        
                        # Force update of display to show error icons
                        group_widget._update_overall_progress_display()
                        
                        self.items_layout.addWidget(group_widget)
                        self.active_album_groups[failed_item['album_id']] = group_widget
                        
                    elif failed_item['type'] == 'playlist':
                        group_widget = PlaylistGroupItemWidget(
                            playlist_id=failed_item['playlist_id'],
                            playlist_title=failed_item['playlist_title'],
                            total_tracks=len(failed_item['failed_tracks'])
                        )
                        
                        # Connect group retry signal
                        group_widget.retry_failed_tracks.connect(self._handle_group_retry)
                        
                        for track in failed_item['failed_tracks']:
                            group_widget.add_track(track['track_id'], track['title'])
                            group_widget.handle_track_failed(track['track_id'], track.get('error_message', 'Unknown error'))
                            # Add to track mapping for proper signal routing
                            self.track_to_group_map[track['track_id']] = {'type': 'playlist', 'group_id': failed_item['playlist_id']}
                        
                        # Force update of display to show error icons
                        group_widget._update_overall_progress_display()
                        
                        self.items_layout.addWidget(group_widget)
                        self.active_playlist_groups[failed_item['playlist_id']] = group_widget
                
                logger.info(f"[DownloadQueueWidget] Loaded {len(failed_downloads)} failed downloads from previous session")
            
        except Exception as e:
            logger.error(f"[DownloadQueueWidget] Failed to load queue state: {e}")

    def clear_queue_state_file(self):
        """Clears the saved queue state file."""
        try:
            file_path = Path('download_queue_state.json')
            if file_path.exists():
                file_path.unlink()
                logger.debug("[DownloadQueueWidget] Queue state file cleared")
        except Exception as e:
            logger.error(f"[DownloadQueueWidget] Failed to clear queue state file: {e}")

    def _handle_individual_retry(self, track_id_str: str):
        logger.info(f"[DownloadQueueWidget] Individual retry requested for track: {track_id_str}")
        if track_id_str in self.active_individual_tracks:
            widget = self.active_individual_tracks[track_id_str]
            widget.setStyleSheet("") 
            widget.progress_bar.setValue(0)
            widget.progress_bar.setFormat("Pending...")
            widget.status = "pending"
            try:
                numeric_item_id = int(track_id_str)
                # Assuming download_track exists and takes numeric ID for individual tracks
                self.download_manager.download_track(numeric_item_id) 
            except Exception as e:
                logger.error(f"Error retrying track {track_id_str}: {e}")
                widget.status = "failed"
                widget.progress_bar.setFormat("Error: Retry failed")
        else:
            logger.warning(f"[DownloadQueueWidget] Individual retry requested for unknown track_id: {track_id_str}")

    def _handle_group_retry(self, group_id: str, failed_track_ids: list):
        logger.info(f"[DownloadQueueWidget] Group retry requested for group: {group_id}, failed tracks: {failed_track_ids}")
        
        if not self.download_manager:
            logger.error("[DownloadQueueWidget] DownloadManager not available for group retry.")
            return
            
        if group_id in self.active_album_groups:
            group_widget = self.active_album_groups[group_id]
            # Reset only the failed tracks
            for track_id in failed_track_ids:
                if track_id in group_widget.tracks:
                    track_info = group_widget.tracks[track_id]
                    track_info['status'] = 'pending'
                    track_info['progress'] = 0
                    track_info['error'] = None
                    
            # Decrease failed count since we're retrying them
            group_widget.failed_tracks_count -= len(failed_track_ids)
            group_widget._update_overall_progress_display()
            
            # Retry downloads for failed tracks
            for track_id in failed_track_ids:
                try:
                    numeric_track_id = int(track_id)
                    self.download_manager._queue_individual_track_download(
                        track_id=numeric_track_id,
                        item_type='album_track',
                        album_id=int(group_id),
                        album_total_tracks=group_widget.total_tracks
                    )
                except Exception as e:
                    logger.error(f"Error retrying album track {track_id}: {e}")
                    
        elif group_id in self.active_playlist_groups:
            group_widget = self.active_playlist_groups[group_id]
            # Reset only the failed tracks
            for track_id in failed_track_ids:
                if track_id in group_widget.tracks:
                    track_info = group_widget.tracks[track_id]
                    track_info['status'] = 'pending'
                    track_info['progress'] = 0
                    track_info['error'] = None
                    
            # Decrease failed count since we're retrying them
            group_widget.failed_tracks_count -= len(failed_track_ids)
            group_widget._update_overall_progress_display()
            
            # Retry downloads for failed tracks
            for track_id in failed_track_ids:
                try:
                    numeric_track_id = int(track_id)
                    self.download_manager._queue_individual_track_download(
                        track_id=numeric_track_id,
                        item_type='playlist_track',
                        playlist_id=int(group_id),
                        playlist_title=group_widget.playlist_title,
                        playlist_total_tracks=group_widget.total_tracks
                    )
                except Exception as e:
                    logger.error(f"Error retrying playlist track {track_id}: {e}")
                    
        else:
            logger.warning(f"[DownloadQueueWidget] Group retry requested for unknown group_id: {group_id}")

# Remove standalone test if it's causing issues with relative imports or if not needed anymore
# if __name__ == '__main__':
#     from PyQt6.QtWidgets import QApplication
#     # from .components.download_item_widget import DownloadItemWidget # Already imported above
#     import sys
#     class DummyDM:
#         class Signals(QObject):
#             download_started = pyqtSignal(dict)
#             download_progress = pyqtSignal(str, int)
#             download_finished = pyqtSignal(str)
#             download_failed = pyqtSignal(str, str)
#         def __init__(self):
#             self.signals = self.Signals()
#             logger.info("DummyDM created with signals")

#     app = QApplication(sys.argv)
#     logging.basicConfig(level=logging.DEBUG)
    
#     dummy_dm = DummyDM()
#     queue_widget = DownloadQueueWidget(dummy_dm) 
    
#     queue_widget.show()
#     queue_widget.resize(300, 600)

#     # Simulate signals
#     import time
#     from PyQt6.QtCore import QTimer

#     def sim_downloads():
#         dummy_dm.signals.download_started.emit({'id': 'track_001', 'title': 'Simulated Song One', 'type': 'track'})
#         dummy_dm.signals.download_progress.emit('track_001', 30)
        
#         dummy_dm.signals.download_started.emit({'id': 'album_002', 'title': 'Simulated Album Two', 'type': 'album'})
#         dummy_dm.signals.download_progress.emit('track_001', 70)
#         dummy_dm.signals.download_progress.emit('album_002', 20)

#         dummy_dm.signals.download_finished.emit('track_001')
#         dummy_dm.signals.download_failed.emit('album_002', "Simulated Network Timeout")

#     QTimer.singleShot(1000, sim_downloads) # Simulate after 1 sec

#     sys.exit(app.exec()) 