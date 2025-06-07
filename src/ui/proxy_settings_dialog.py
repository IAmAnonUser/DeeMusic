"""Proxy Settings Dialog for DeeMusic."""

import logging
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QCheckBox, QComboBox, QLineEdit, QPushButton, QLabel,
    QDialogButtonBox, QMessageBox, QSpacerItem, QSizePolicy
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

logger = logging.getLogger(__name__)

class ProxySettingsDialog(QDialog):
    """Dialog for configuring proxy settings."""
    
    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.config = config_manager
        self.setWindowTitle("Proxy Settings")
        self.setModal(True)
        self.setMinimumSize(450, 350)
        self.resize(500, 400)
        
        self._setup_ui()
        self._load_settings()
        
    def _setup_ui(self):
        """Set up the user interface."""
        layout = QVBoxLayout(self)
        
        # Title and description
        title_label = QLabel("Proxy Configuration")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)
        
        desc_label = QLabel(
            "Configure proxy settings to bypass geo-restrictions.\n"
            "Note: Only use proxies you trust. These settings will route all API traffic through the proxy."
        )
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: #666; margin-bottom: 10px;")
        layout.addWidget(desc_label)
        
        # Proxy settings group
        proxy_group = QGroupBox("Proxy Settings")
        proxy_layout = QVBoxLayout(proxy_group)
        
        # Enable proxy checkbox
        self.enable_proxy_cb = QCheckBox("Enable Proxy")
        self.enable_proxy_cb.stateChanged.connect(self._on_enable_changed)
        proxy_layout.addWidget(self.enable_proxy_cb)
        
        # Proxy configuration form
        form_layout = QFormLayout()
        
        # Proxy type
        self.proxy_type_combo = QComboBox()
        self.proxy_type_combo.addItems(["http", "https", "socks4", "socks5"])
        form_layout.addRow("Type:", self.proxy_type_combo)
        
        # Host and port
        host_port_layout = QHBoxLayout()
        self.host_edit = QLineEdit()
        self.host_edit.setPlaceholderText("proxy.example.com")
        self.port_edit = QLineEdit()
        self.port_edit.setPlaceholderText("8080")
        self.port_edit.setMaximumWidth(80)
        host_port_layout.addWidget(self.host_edit)
        host_port_layout.addWidget(QLabel(":"))
        host_port_layout.addWidget(self.port_edit)
        host_port_layout.addStretch()
        form_layout.addRow("Host:Port:", host_port_layout)
        
        # Username and password (optional)
        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("Optional")
        form_layout.addRow("Username:", self.username_edit)
        
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText("Optional")
        form_layout.addRow("Password:", self.password_edit)
        
        proxy_layout.addLayout(form_layout)
        
        # Usage options
        usage_layout = QVBoxLayout()
        self.use_for_api_cb = QCheckBox("Use for API requests")
        self.use_for_api_cb.setChecked(True)
        self.use_for_downloads_cb = QCheckBox("Use for file downloads")
        self.use_for_downloads_cb.setChecked(True)
        
        usage_layout.addWidget(self.use_for_api_cb)
        usage_layout.addWidget(self.use_for_downloads_cb)
        proxy_layout.addLayout(usage_layout)
        
        layout.addWidget(proxy_group)
        
        # Test connection button
        test_layout = QHBoxLayout()
        self.test_button = QPushButton("Test Connection")
        self.test_button.clicked.connect(self._test_connection)
        test_layout.addWidget(self.test_button)
        test_layout.addStretch()
        layout.addLayout(test_layout)
        
        # Spacer
        layout.addItem(QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))
        
        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel |
            QDialogButtonBox.StandardButton.Apply
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        button_box.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self._apply_settings)
        layout.addWidget(button_box)
        
        # Initially disable proxy settings
        self._on_enable_changed()
        
    def _load_settings(self):
        """Load settings from config manager."""
        proxy_config = self.config.get_setting('network.proxy', {})
        
        self.enable_proxy_cb.setChecked(proxy_config.get('enabled', False))
        self.proxy_type_combo.setCurrentText(proxy_config.get('type', 'http'))
        self.host_edit.setText(proxy_config.get('host', ''))
        self.port_edit.setText(str(proxy_config.get('port', '')))
        self.username_edit.setText(proxy_config.get('username', ''))
        self.password_edit.setText(proxy_config.get('password', ''))
        self.use_for_api_cb.setChecked(proxy_config.get('use_for_api', True))
        self.use_for_downloads_cb.setChecked(proxy_config.get('use_for_downloads', True))
        
    def _on_enable_changed(self):
        """Handle enable/disable of proxy settings."""
        enabled = self.enable_proxy_cb.isChecked()
        self.proxy_type_combo.setEnabled(enabled)
        self.host_edit.setEnabled(enabled)
        self.port_edit.setEnabled(enabled)
        self.username_edit.setEnabled(enabled)
        self.password_edit.setEnabled(enabled)
        self.use_for_api_cb.setEnabled(enabled)
        self.use_for_downloads_cb.setEnabled(enabled)
        self.test_button.setEnabled(enabled)
        
    def _test_connection(self):
        """Test the proxy connection."""
        if not self.enable_proxy_cb.isChecked():
            return
            
        host = self.host_edit.text().strip()
        port = self.port_edit.text().strip()
        
        if not host or not port:
            QMessageBox.warning(self, "Invalid Settings", "Please enter both host and port.")
            return
            
        # Simple test - try to connect to Google
        import requests
        import time
        
        proxy_type = self.proxy_type_combo.currentText()
        username = self.username_edit.text().strip()
        password = self.password_edit.text().strip()
        
        # Build proxy URL
        if username and password:
            proxy_url = f"{proxy_type}://{username}:{password}@{host}:{port}"
        else:
            proxy_url = f"{proxy_type}://{host}:{port}"
            
        proxies = {
            'http': proxy_url,
            'https': proxy_url
        }
        
        try:
            self.test_button.setText("Testing...")
            self.test_button.setEnabled(False)
            
            # Test with a simple HTTP request
            start_time = time.time()
            response = requests.get('http://httpbin.org/ip', proxies=proxies, timeout=10)
            elapsed = time.time() - start_time
            
            if response.status_code == 200:
                QMessageBox.information(
                    self, 
                    "Connection Success", 
                    f"Proxy connection successful!\n"
                    f"Response time: {elapsed:.2f}s\n"
                    f"Your IP via proxy: {response.json().get('origin', 'Unknown')}"
                )
            else:
                QMessageBox.warning(
                    self, 
                    "Connection Failed", 
                    f"Proxy test failed with status code: {response.status_code}"
                )
                
        except Exception as e:
            QMessageBox.critical(
                self, 
                "Connection Error", 
                f"Failed to connect through proxy:\n{str(e)}"
            )
        finally:
            self.test_button.setText("Test Connection")
            self.test_button.setEnabled(True)
            
    def _apply_settings(self):
        """Apply settings without closing dialog."""
        self._save_settings()
        QMessageBox.information(self, "Settings Applied", "Proxy settings have been saved.")
        
    def _save_settings(self):
        """Save settings to config manager."""
        proxy_config = {
            'enabled': self.enable_proxy_cb.isChecked(),
            'type': self.proxy_type_combo.currentText(),
            'host': self.host_edit.text().strip(),
            'port': self.port_edit.text().strip(),
            'username': self.username_edit.text().strip(),
            'password': self.password_edit.text().strip(),
            'use_for_api': self.use_for_api_cb.isChecked(),
            'use_for_downloads': self.use_for_downloads_cb.isChecked()
        }
        
        self.config.set_setting('network.proxy', proxy_config)
        self.config.save_config()
        logger.info(f"Proxy settings saved: enabled={proxy_config['enabled']}, host={proxy_config.get('host', 'N/A')}")
        
    def accept(self):
        """Accept dialog and save settings."""
        self._save_settings()
        super().accept() 