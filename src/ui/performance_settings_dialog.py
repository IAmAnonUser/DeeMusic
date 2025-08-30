"""Performance settings dialog for advanced users."""

import logging
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                            QSpinBox, QCheckBox, QComboBox, QPushButton,
                            QGroupBox, QGridLayout, QTextEdit, QTabWidget,
                            QWidget, QProgressBar, QSlider)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from src.utils.system_resources import get_resource_manager
from src.utils.performance_monitor import get_performance_monitor
from src.utils.startup_optimizer import get_optimization_report

logger = logging.getLogger(__name__)

class PerformanceSettingsDialog(QDialog):
    """Advanced performance settings dialog."""
    
    settings_changed = pyqtSignal(dict)
    
    def __init__(self, config_manager, parent=None):
        super().__init__(parent)
        self.config = config_manager
        self.resource_manager = get_resource_manager()
        self.performance_monitor = get_performance_monitor()
        
        self.setWindowTitle("Performance Settings")
        self.setMinimumSize(600, 500)
        self.setup_ui()
        self.load_settings()
        
        # Update system info periodically
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_system_info)
        self.update_timer.start(5000)  # FLASHING FIX: Update every 5 seconds instead of 2
    
    def setup_ui(self):
        """Set up the user interface."""
        layout = QVBoxLayout(self)
        
        # Create tab widget
        tab_widget = QTabWidget()
        
        # Performance tab
        performance_tab = self.create_performance_tab()
        tab_widget.addTab(performance_tab, "Performance")
        
        # System Info tab
        system_info_tab = self.create_system_info_tab()
        tab_widget.addTab(system_info_tab, "System Info")
        
        # Advanced tab
        advanced_tab = self.create_advanced_tab()
        tab_widget.addTab(advanced_tab, "Advanced")
        
        layout.addWidget(tab_widget)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.auto_optimize_btn = QPushButton("Auto Optimize")
        self.auto_optimize_btn.clicked.connect(self.auto_optimize)
        
        self.reset_btn = QPushButton("Reset to Defaults")
        self.reset_btn.clicked.connect(self.reset_to_defaults)
        
        self.apply_btn = QPushButton("Apply")
        self.apply_btn.clicked.connect(self.apply_settings)
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        
        button_layout.addWidget(self.auto_optimize_btn)
        button_layout.addWidget(self.reset_btn)
        button_layout.addStretch()
        button_layout.addWidget(self.apply_btn)
        button_layout.addWidget(self.cancel_btn)
        
        layout.addLayout(button_layout)
    
    def create_performance_tab(self) -> QWidget:
        """Create the performance settings tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Download settings
        download_group = QGroupBox("Download Performance")
        download_layout = QGridLayout(download_group)
        
        download_layout.addWidget(QLabel("Concurrent Downloads:"), 0, 0)
        self.concurrent_downloads_spin = QSpinBox()
        self.concurrent_downloads_spin.setRange(1, 5)  # Maximum 5 for system stability
        download_layout.addWidget(self.concurrent_downloads_spin, 0, 1)
        
        download_layout.addWidget(QLabel("Thread Pool Size:"), 1, 0)
        self.thread_pool_spin = QSpinBox()
        self.thread_pool_spin.setRange(1, 100)
        download_layout.addWidget(self.thread_pool_spin, 1, 1)
        
        download_layout.addWidget(QLabel("Batch Size:"), 2, 0)
        self.batch_size_spin = QSpinBox()
        self.batch_size_spin.setRange(1, 20)
        download_layout.addWidget(self.batch_size_spin, 2, 1)
        
        layout.addWidget(download_group)
        
        # Memory settings
        memory_group = QGroupBox("Memory Management")
        memory_layout = QGridLayout(memory_group)
        
        memory_layout.addWidget(QLabel("Memory Cache (MB):"), 0, 0)
        self.memory_cache_spin = QSpinBox()
        self.memory_cache_spin.setRange(32, 4096)
        memory_layout.addWidget(self.memory_cache_spin, 0, 1)
        
        memory_layout.addWidget(QLabel("Image Cache Size:"), 1, 0)
        self.image_cache_spin = QSpinBox()
        self.image_cache_spin.setRange(10, 2000)
        memory_layout.addWidget(self.image_cache_spin, 1, 1)
        
        layout.addWidget(memory_group)
        
        # UI settings
        ui_group = QGroupBox("User Interface")
        ui_layout = QGridLayout(ui_group)
        
        ui_layout.addWidget(QLabel("Update Interval (ms):"), 0, 0)
        self.ui_update_spin = QSpinBox()
        self.ui_update_spin.setRange(10, 1000)
        ui_layout.addWidget(self.ui_update_spin, 0, 1)
        
        self.gpu_acceleration_check = QCheckBox("Enable GPU Acceleration")
        ui_layout.addWidget(self.gpu_acceleration_check, 1, 0, 1, 2)
        
        self.preload_content_check = QCheckBox("Preload Content")
        ui_layout.addWidget(self.preload_content_check, 2, 0, 1, 2)
        
        layout.addWidget(ui_group)
        
        layout.addStretch()
        return widget
    
    def create_system_info_tab(self) -> QWidget:
        """Create the system information tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # System specs
        specs_group = QGroupBox("System Specifications")
        specs_layout = QGridLayout(specs_group)
        
        system_info = self.resource_manager.system_info
        
        specs_layout.addWidget(QLabel("CPU Cores:"), 0, 0)
        specs_layout.addWidget(QLabel(f"{system_info['cpu']['logical_cores']} logical, {system_info['cpu']['physical_cores']} physical"), 0, 1)
        
        specs_layout.addWidget(QLabel("Total Memory:"), 1, 0)
        specs_layout.addWidget(QLabel(f"{system_info['memory']['total_gb']:.1f} GB"), 1, 1)
        
        specs_layout.addWidget(QLabel("Performance Profile:"), 2, 0)
        specs_layout.addWidget(QLabel(self.resource_manager.performance_profile.title()), 2, 1)
        
        specs_layout.addWidget(QLabel("GPU Available:"), 3, 0)
        gpu_text = "Yes" if system_info['gpu']['available'] else "No"
        specs_layout.addWidget(QLabel(gpu_text), 3, 1)
        
        layout.addWidget(specs_group)
        
        # Current usage
        usage_group = QGroupBox("Current Usage")
        usage_layout = QVBoxLayout(usage_group)
        
        self.cpu_progress = QProgressBar()
        self.cpu_progress.setRange(0, 100)
        usage_layout.addWidget(QLabel("CPU Usage:"))
        usage_layout.addWidget(self.cpu_progress)
        
        self.memory_progress = QProgressBar()
        self.memory_progress.setRange(0, 100)
        usage_layout.addWidget(QLabel("Memory Usage:"))
        usage_layout.addWidget(self.memory_progress)
        
        self.usage_label = QLabel()
        usage_layout.addWidget(self.usage_label)
        
        layout.addWidget(usage_group)
        
        layout.addStretch()
        return widget
    
    def create_advanced_tab(self) -> QWidget:
        """Create the advanced settings tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Network settings
        network_group = QGroupBox("Network Settings")
        network_layout = QGridLayout(network_group)
        
        network_layout.addWidget(QLabel("Network Timeout (s):"), 0, 0)
        self.network_timeout_spin = QSpinBox()
        self.network_timeout_spin.setRange(5, 120)
        network_layout.addWidget(self.network_timeout_spin, 0, 1)
        
        network_layout.addWidget(QLabel("Retry Attempts:"), 1, 0)
        self.retry_attempts_spin = QSpinBox()
        self.retry_attempts_spin.setRange(1, 10)
        network_layout.addWidget(self.retry_attempts_spin, 1, 1)
        
        layout.addWidget(network_group)
        
        # Optimization report
        report_group = QGroupBox("Optimization Report")
        report_layout = QVBoxLayout(report_group)
        
        self.report_text = QTextEdit()
        self.report_text.setReadOnly(True)
        self.report_text.setMaximumHeight(200)
        report_layout.addWidget(self.report_text)
        
        refresh_report_btn = QPushButton("Refresh Report")
        refresh_report_btn.clicked.connect(self.update_optimization_report)
        report_layout.addWidget(refresh_report_btn)
        
        layout.addWidget(report_group)
        
        layout.addStretch()
        return widget
    
    def load_settings(self):
        """Load current settings into the UI."""
        optimal_settings = self.resource_manager.get_optimal_settings()
        
        # Load current or optimal settings
        self.concurrent_downloads_spin.setValue(
            self.config.get_setting('downloads.concurrent_downloads', optimal_settings['concurrent_downloads'])
        )
        self.thread_pool_spin.setValue(optimal_settings['thread_pool_size'])
        self.batch_size_spin.setValue(optimal_settings['batch_size'])
        self.memory_cache_spin.setValue(optimal_settings['memory_cache_mb'])
        self.image_cache_spin.setValue(optimal_settings['image_cache_size'])
        self.ui_update_spin.setValue(optimal_settings['ui_update_interval'])
        self.network_timeout_spin.setValue(optimal_settings['network_timeout'])
        self.retry_attempts_spin.setValue(optimal_settings['retry_attempts'])
        
        self.gpu_acceleration_check.setChecked(optimal_settings.get('enable_gpu_acceleration', False))
        self.preload_content_check.setChecked(optimal_settings.get('preload_content', True))
        
        self.update_optimization_report()
    
    def update_system_info(self):
        """Update system information display."""
        try:
            usage = self.resource_manager.get_current_resource_usage()
            
            self.cpu_progress.setValue(int(usage.get('cpu_percent', 0)))
            self.memory_progress.setValue(int(usage.get('memory_percent', 0)))
            
            self.usage_label.setText(
                f"Available Memory: {usage.get('memory_available_gb', 0):.1f} GB"
            )
        except Exception as e:
            logger.error(f"Error updating system info: {e}")
    
    def update_optimization_report(self):
        """Update the optimization report."""
        try:
            report = get_optimization_report()
            
            report_text = f"Performance Profile: {report['performance_profile'].title()}\n\n"
            report_text += f"Applied Optimizations:\n"
            for opt in report['optimizations_applied']:
                report_text += f"  • {opt.replace('_', ' ').title()}\n"
            
            report_text += f"\nOptimal Settings:\n"
            for key, value in report['optimal_settings'].items():
                if isinstance(value, (int, float, bool)):
                    report_text += f"  • {key.replace('_', ' ').title()}: {value}\n"
            
            self.report_text.setPlainText(report_text)
        except Exception as e:
            logger.error(f"Error updating optimization report: {e}")
            self.report_text.setPlainText(f"Error generating report: {e}")
    
    def auto_optimize(self):
        """Apply automatic optimization."""
        optimal_settings = self.resource_manager.get_optimal_settings()
        
        self.concurrent_downloads_spin.setValue(optimal_settings['concurrent_downloads'])
        self.thread_pool_spin.setValue(optimal_settings['thread_pool_size'])
        self.batch_size_spin.setValue(optimal_settings['batch_size'])
        self.memory_cache_spin.setValue(optimal_settings['memory_cache_mb'])
        self.image_cache_spin.setValue(optimal_settings['image_cache_size'])
        self.ui_update_spin.setValue(optimal_settings['ui_update_interval'])
        self.network_timeout_spin.setValue(optimal_settings['network_timeout'])
        self.retry_attempts_spin.setValue(optimal_settings['retry_attempts'])
        
        self.gpu_acceleration_check.setChecked(optimal_settings.get('enable_gpu_acceleration', False))
        self.preload_content_check.setChecked(optimal_settings.get('preload_content', True))
        
        logger.info("Applied automatic optimization settings")
    
    def reset_to_defaults(self):
        """Reset all settings to defaults."""
        # Reset to minimal safe defaults
        self.concurrent_downloads_spin.setValue(3)
        self.thread_pool_spin.setValue(4)
        self.batch_size_spin.setValue(3)
        self.memory_cache_spin.setValue(128)
        self.image_cache_spin.setValue(100)
        self.ui_update_spin.setValue(100)
        self.network_timeout_spin.setValue(30)
        self.retry_attempts_spin.setValue(3)
        
        self.gpu_acceleration_check.setChecked(False)
        self.preload_content_check.setChecked(True)
        
        logger.info("Reset settings to defaults")
    
    def apply_settings(self):
        """Apply the current settings."""
        settings = {
            'concurrent_downloads': min(self.concurrent_downloads_spin.value(), 5),  # Cap at 5 for stability
            'thread_pool_size': self.thread_pool_spin.value(),
            'batch_size': self.batch_size_spin.value(),
            'memory_cache_mb': self.memory_cache_spin.value(),
            'image_cache_size': self.image_cache_spin.value(),
            'ui_update_interval': self.ui_update_spin.value(),
            'network_timeout': self.network_timeout_spin.value(),
            'retry_attempts': self.retry_attempts_spin.value(),
            'enable_gpu_acceleration': self.gpu_acceleration_check.isChecked(),
            'preload_content': self.preload_content_check.isChecked(),
        }
        
        # Save to config
        self.config.set_setting('downloads.concurrent_downloads', settings['concurrent_downloads'])
        
        # Emit signal for other components to update
        self.settings_changed.emit(settings)
        
        logger.info(f"Applied performance settings: {settings}")
        self.accept()
    
    def closeEvent(self, event):
        """Clean up when dialog is closed."""
        self.update_timer.stop()
        super().closeEvent(event)