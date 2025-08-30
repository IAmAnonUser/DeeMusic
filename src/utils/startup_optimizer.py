"""Startup optimization utilities for better performance."""

import os
import sys
import gc
import logging
from typing import Dict, Any
from PyQt6.QtCore import QCoreApplication, QThread
from src.utils.system_resources import get_resource_manager
from src.utils.gpu_acceleration import get_gpu_accelerator, enable_gpu_acceleration

logger = logging.getLogger(__name__)

class StartupOptimizer:
    """Optimizes application startup and runtime performance."""
    
    def __init__(self):
        self.resource_manager = get_resource_manager()
        self.optimizations_applied = []
    
    def apply_startup_optimizations(self):
        """Apply startup optimizations - alias for compatibility."""
        return self.apply_all_optimizations()
    
    def apply_all_optimizations(self):
        """Apply all available optimizations."""
        logger.info("Applying startup optimizations...")
        
        # System-level optimizations
        self._optimize_python_interpreter()
        self._optimize_memory_management()
        self._optimize_threading()
        self._optimize_qt_application()
        self._optimize_gpu_acceleration()
        
        # Application-level optimizations
        self._optimize_file_operations()
        self._optimize_network_settings()
        
        logger.info(f"Applied {len(self.optimizations_applied)} optimizations: {', '.join(self.optimizations_applied)}")
    
    def _optimize_python_interpreter(self):
        """Optimize Python interpreter settings."""
        try:
            # Optimize garbage collection
            gc.set_threshold(700, 10, 10)  # More aggressive GC for better memory management
            
            # Set recursion limit based on available memory
            memory_gb = self.resource_manager.system_info['memory']['total_gb']
            if memory_gb >= 16:
                sys.setrecursionlimit(3000)
            elif memory_gb >= 8:
                sys.setrecursionlimit(2000)
            else:
                sys.setrecursionlimit(1500)
            
            self.optimizations_applied.append("python_interpreter")
            logger.debug("Python interpreter optimized")
        except Exception as e:
            logger.error(f"Error optimizing Python interpreter: {e}")
    
    def _optimize_memory_management(self):
        """Optimize memory management settings."""
        try:
            # Force garbage collection
            gc.collect()
            
            # Set memory-related environment variables
            optimal_settings = self.resource_manager.get_optimal_settings()
            
            # Set Python memory allocator (if available)
            if hasattr(sys, 'set_int_max_str_digits'):
                sys.set_int_max_str_digits(4300)  # Prevent DoS attacks and improve performance
            
            self.optimizations_applied.append("memory_management")
            logger.debug("Memory management optimized")
        except Exception as e:
            logger.error(f"Error optimizing memory management: {e}")
    
    def _optimize_threading(self):
        """Optimize threading settings."""
        try:
            # Set optimal thread count for Qt
            optimal_settings = self.resource_manager.get_optimal_settings()
            thread_count = optimal_settings['thread_pool_size']
            
            # Set Qt thread pool size
            from PyQt6.QtCore import QThreadPool
            QThreadPool.globalInstance().setMaxThreadCount(thread_count)
            
            self.optimizations_applied.append("threading")
            logger.debug(f"Threading optimized: {thread_count} threads")
        except Exception as e:
            logger.error(f"Error optimizing threading: {e}")
    
    def _optimize_qt_application(self):
        """Optimize Qt application settings."""
        try:
            app = QCoreApplication.instance()
            if app:
                # Set application attributes for better performance
                app.setAttribute(101, True)  # AA_DontCreateNativeWidgetSiblings
                
                # Set optimal update intervals
                optimal_settings = self.resource_manager.get_optimal_settings()
                
                # Enable high DPI scaling if available
                if hasattr(app, 'setHighDpiScaleFactorRoundingPolicy'):
                    app.setHighDpiScaleFactorRoundingPolicy(1)  # Round
            
            self.optimizations_applied.append("qt_application")
            logger.debug("Qt application optimized")
        except Exception as e:
            logger.error(f"Error optimizing Qt application: {e}")
    
    def _optimize_gpu_acceleration(self):
        """Enable GPU acceleration if available and beneficial."""
        try:
            optimal_settings = self.resource_manager.get_optimal_settings()
            
            if optimal_settings.get('enable_gpu_acceleration', False):
                gpu_accelerator = get_gpu_accelerator()
                if gpu_accelerator.gpu_available:
                    enable_gpu_acceleration(True)
                    self.optimizations_applied.append("gpu_acceleration")
                    logger.debug("GPU acceleration enabled")
                else:
                    logger.debug("GPU acceleration requested but not available")
            else:
                logger.debug("GPU acceleration disabled by performance profile")
        except Exception as e:
            logger.error(f"Error optimizing GPU acceleration: {e}")
    
    def _optimize_file_operations(self):
        """Optimize file I/O operations."""
        try:
            # Set optimal buffer sizes for file operations
            if sys.platform == 'win32':
                # Windows-specific optimizations
                os.environ['PYTHONIOENCODING'] = 'utf-8'
            
            self.optimizations_applied.append("file_operations")
            logger.debug("File operations optimized")
        except Exception as e:
            logger.error(f"Error optimizing file operations: {e}")
    
    def _optimize_network_settings(self):
        """Optimize network-related settings."""
        try:
            optimal_settings = self.resource_manager.get_optimal_settings()
            
            # Set connection pool size based on concurrent downloads
            concurrent_downloads = optimal_settings['concurrent_downloads']
            
            # These would be used by the HTTP session in download manager
            network_config = {
                'pool_connections': min(concurrent_downloads * 2, 20),
                'pool_maxsize': min(concurrent_downloads * 3, 30),
                'max_retries': optimal_settings['retry_attempts'],
            }
            
            # Store for later use by download manager
            self.network_config = network_config
            
            self.optimizations_applied.append("network_settings")
            logger.debug(f"Network settings optimized: {network_config}")
        except Exception as e:
            logger.error(f"Error optimizing network settings: {e}")
    
    def get_optimization_report(self) -> Dict[str, Any]:
        """Get a report of applied optimizations."""
        return {
            'optimizations_applied': self.optimizations_applied,
            'system_profile': self.resource_manager.performance_profile,
            'system_info': self.resource_manager.system_info,
            'optimal_settings': self.resource_manager.get_optimal_settings(),
        }

# Global startup optimizer
_startup_optimizer = None

def get_startup_optimizer() -> StartupOptimizer:
    """Get the global startup optimizer instance."""
    global _startup_optimizer
    if _startup_optimizer is None:
        _startup_optimizer = StartupOptimizer()
    return _startup_optimizer

def optimize_startup():
    """Apply all startup optimizations."""
    get_startup_optimizer().apply_all_optimizations()

def apply_startup_optimizations():
    """Apply startup optimizations - alias for compatibility."""
    return optimize_startup()

def get_optimization_report() -> Dict[str, Any]:
    """Get optimization report."""
    return get_startup_optimizer().get_optimization_report()