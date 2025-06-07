from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QSpinBox, QDoubleSpinBox, QPushButton, QGroupBox,
    QFormLayout
)
from PyQt6.QtCore import Qt, pyqtSignal

class RetrySettingsWidget(QWidget):
    """Widget for configuring download retry settings."""
    
    settings_changed = pyqtSignal()
    
    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self._init_ui()
        self._load_settings()
        
    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        # Create retry settings group
        group = QGroupBox("Download Retry Settings")
        form = QFormLayout()
        
        # Max retries
        self.max_retries = QSpinBox()
        self.max_retries.setRange(0, 10)
        self.max_retries.setToolTip("Maximum number of retry attempts")
        self.max_retries.valueChanged.connect(self._on_settings_changed)
        form.addRow("Max Retries:", self.max_retries)
        
        # Initial delay
        self.initial_delay = QDoubleSpinBox()
        self.initial_delay.setRange(0.1, 30.0)
        self.initial_delay.setSingleStep(0.5)
        self.initial_delay.setToolTip("Initial delay between retries (seconds)")
        self.initial_delay.valueChanged.connect(self._on_settings_changed)
        form.addRow("Initial Delay (s):", self.initial_delay)
        
        # Max delay
        self.max_delay = QDoubleSpinBox()
        self.max_delay.setRange(1.0, 300.0)
        self.max_delay.setSingleStep(5.0)
        self.max_delay.setToolTip("Maximum delay between retries (seconds)")
        self.max_delay.valueChanged.connect(self._on_settings_changed)
        form.addRow("Max Delay (s):", self.max_delay)
        
        # Backoff factor
        self.backoff_factor = QDoubleSpinBox()
        self.backoff_factor.setRange(1.0, 5.0)
        self.backoff_factor.setSingleStep(0.1)
        self.backoff_factor.setToolTip("Multiplier for delay between retries")
        self.backoff_factor.valueChanged.connect(self._on_settings_changed)
        form.addRow("Backoff Factor:", self.backoff_factor)
        
        group.setLayout(form)
        layout.addWidget(group)
        
        # Add apply and reset buttons
        button_layout = QHBoxLayout()
        
        self.reset_button = QPushButton("Reset to Defaults")
        self.reset_button.clicked.connect(self._reset_settings)
        button_layout.addWidget(self.reset_button)
        
        self.apply_button = QPushButton("Apply")
        self.apply_button.clicked.connect(self._apply_settings)
        button_layout.addWidget(self.apply_button)
        
        layout.addLayout(button_layout)
        layout.addStretch()
        
    def _load_settings(self):
        """Load current settings into UI."""
        settings = self.config_manager.retry_settings
        self.max_retries.setValue(settings.max_retries)
        self.initial_delay.setValue(settings.initial_delay)
        self.max_delay.setValue(settings.max_delay)
        self.backoff_factor.setValue(settings.backoff_factor)
        
    def _on_settings_changed(self):
        """Handle settings changes."""
        self.apply_button.setEnabled(True)
        
    def _apply_settings(self):
        """Apply current settings."""
        self.config_manager.update_retry_settings(
            max_retries=self.max_retries.value(),
            initial_delay=self.initial_delay.value(),
            max_delay=self.max_delay.value(),
            backoff_factor=self.backoff_factor.value()
        )
        self.apply_button.setEnabled(False)
        self.settings_changed.emit()
        
    def _reset_settings(self):
        """Reset settings to defaults."""
        self.max_retries.setValue(3)
        self.initial_delay.setValue(1.0)
        self.max_delay.setValue(60.0)
        self.backoff_factor.setValue(2.0)
        self._apply_settings() 