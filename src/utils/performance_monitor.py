"""Performance monitoring and dynamic optimization."""

import logging
import time
from typing import Dict, Any, Optional, Callable
from PyQt6.QtCore import QTimer, QObject, pyqtSignal
from src.utils.system_resources import get_resource_manager

logger = logging.getLogger(__name__)

class PerformanceMonitor(QObject):
    """Monitors system performance and dynamically adjusts application settings."""
    
    # Signals for performance events
    performance_changed = pyqtSignal(dict)  # Emits new performance settings
    throttle_requested = pyqtSignal(bool)   # Emits True to throttle, False to resume
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.resource_manager = get_resource_manager()
        self.monitoring_enabled = True
        self.last_optimization = 0
        self.optimization_callbacks = []
        
        # Initialize timers but don't start them immediately
        self.monitor_timer = None
        self.optimization_timer = None
        
        # Defer timer creation to avoid threading issues
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(1000, self._initialize_timers)
        
        logger.info("Performance monitor initialized")
    
    def _initialize_timers(self):
        """Initialize timers in the main thread."""
        try:
            # Performance monitoring timer
            self.monitor_timer = QTimer()
            self.monitor_timer.timeout.connect(self._monitor_performance)
            
            # Optimization timer (less frequent)
            self.optimization_timer = QTimer()
            self.optimization_timer.timeout.connect(self._optimize_performance)
            
            if self.monitoring_enabled:
                self.monitor_timer.start(5000)  # Check every 5 seconds
                self.optimization_timer.start(30000)  # Optimize every 30 seconds
            
            logger.info("Performance monitor timers initialized")
        except Exception as e:
            logger.error(f"Error initializing performance monitor timers: {e}")
    
    def register_optimization_callback(self, callback: Callable[[Dict[str, Any]], None]):
        """Register a callback to be called when performance settings change."""
        self.optimization_callbacks.append(callback)
    
    def _monitor_performance(self):
        """Monitor current system performance."""
        if not self.monitoring_enabled:
            return
        
        try:
            usage = self.resource_manager.get_current_resource_usage()
            
            # Log performance metrics periodically
            if int(time.time()) % 60 == 0:  # Every minute
                logger.info(f"[PERFORMANCE] CPU: {usage.get('cpu_percent', 0):.1f}%, "
                           f"Memory: {usage.get('memory_percent', 0):.1f}%, "
                           f"Available: {usage.get('memory_available_gb', 0):.1f}GB")
            
            # Check if throttling is needed
            should_throttle = self.resource_manager.should_throttle_operations()
            self.throttle_requested.emit(should_throttle)
            
        except Exception as e:
            logger.error(f"Error monitoring performance: {e}")
    
    def _optimize_performance(self):
        """Optimize performance based on current system state."""
        if not self.monitoring_enabled:
            return
        
        try:
            current_time = time.time()
            
            # Don't optimize too frequently
            if current_time - self.last_optimization < 30:
                return
            
            # Get optimized settings
            optimized_settings = self.resource_manager.optimize_for_current_load()
            
            # Notify callbacks about new settings
            for callback in self.optimization_callbacks:
                try:
                    callback(optimized_settings)
                except Exception as e:
                    logger.error(f"Error in optimization callback: {e}")
            
            # Emit signal
            self.performance_changed.emit(optimized_settings)
            
            self.last_optimization = current_time
            
        except Exception as e:
            logger.error(f"Error optimizing performance: {e}")
    
    def force_optimization(self):
        """Force immediate performance optimization."""
        self.last_optimization = 0
        self._optimize_performance()
    
    def enable_monitoring(self, enabled: bool = True):
        """Enable or disable performance monitoring."""
        self.monitoring_enabled = enabled
        if enabled:
            if self.monitor_timer and self.optimization_timer:
                self.monitor_timer.start(5000)
                self.optimization_timer.start(30000)
                logger.info("Performance monitoring enabled")
            else:
                logger.info("Performance monitoring will be enabled when timers are ready")
        else:
            if self.monitor_timer and self.optimization_timer:
                self.monitor_timer.stop()
                self.optimization_timer.stop()
                logger.info("Performance monitoring disabled")
            else:
                logger.info("Performance monitoring disabled (timers not ready)")
    
    def get_performance_report(self) -> Dict[str, Any]:
        """Get a comprehensive performance report."""
        try:
            system_info = self.resource_manager.system_info
            current_usage = self.resource_manager.get_current_resource_usage()
            optimal_settings = self.resource_manager.get_optimal_settings()
            
            return {
                'system_info': system_info,
                'current_usage': current_usage,
                'optimal_settings': optimal_settings,
                'performance_profile': self.resource_manager.performance_profile,
                'monitoring_enabled': self.monitoring_enabled,
                'last_optimization': self.last_optimization,
            }
        except Exception as e:
            logger.error(f"Error generating performance report: {e}")
            return {}

# Global performance monitor instance
_performance_monitor = None

def get_performance_monitor() -> PerformanceMonitor:
    """Get the global performance monitor instance."""
    global _performance_monitor
    if _performance_monitor is None:
        _performance_monitor = PerformanceMonitor()
    return _performance_monitor

def enable_performance_monitoring(enabled: bool = True):
    """Enable or disable global performance monitoring."""
    get_performance_monitor().enable_monitoring(enabled)

def force_performance_optimization():
    """Force immediate performance optimization."""
    get_performance_monitor().force_optimization()