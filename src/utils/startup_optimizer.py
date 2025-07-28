"""
Startup Optimization Utilities
Provides performance optimizations for the standalone executable.
"""

import os
import sys
import gc
import threading
import time
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class StartupOptimizer:
    """Optimizes application startup performance."""
    
    def __init__(self):
        self.is_frozen = getattr(sys, 'frozen', False)
        self.optimizations_applied = []
    
    def apply_all_optimizations(self):
        """Apply all available startup optimizations."""
        if not self.is_frozen:
            logger.debug("Running from Python - skipping executable optimizations")
            return
        
        logger.info("Applying startup optimizations for standalone executable...")
        
        # Apply optimizations
        self._optimize_python_settings()
        self._optimize_memory_usage()
        self._optimize_threading()
        self._preload_critical_modules()
        self._optimize_file_system_access()
        
        logger.info(f"Applied {len(self.optimizations_applied)} startup optimizations")
    
    def _optimize_python_settings(self):
        """Optimize Python interpreter settings."""
        try:
            # Disable Python's automatic garbage collection during startup
            gc.disable()
            
            # Set optimal garbage collection thresholds
            gc.set_threshold(700, 10, 10)  # More aggressive collection
            
            # Optimize import system
            sys.dont_write_bytecode = True  # Don't write .pyc files
            
            self.optimizations_applied.append("Python settings")
            logger.debug("Applied Python interpreter optimizations")
            
        except Exception as e:
            logger.warning(f"Failed to apply Python optimizations: {e}")
    
    def _optimize_memory_usage(self):
        """Optimize memory usage patterns."""
        try:
            # Force garbage collection to clean up startup overhead
            collected = gc.collect()
            logger.debug(f"Collected {collected} objects during startup optimization")
            
            # Re-enable garbage collection with optimized settings
            gc.enable()
            
            self.optimizations_applied.append("Memory optimization")
            
        except Exception as e:
            logger.warning(f"Failed to apply memory optimizations: {e}")
    
    def _optimize_threading(self):
        """Optimize threading for better performance."""
        try:
            # Set thread stack size for better memory usage
            threading.stack_size(1024 * 1024)  # 1MB stack size
            
            self.optimizations_applied.append("Threading optimization")
            logger.debug("Applied threading optimizations")
            
        except Exception as e:
            logger.warning(f"Failed to apply threading optimizations: {e}")
    
    def _preload_critical_modules(self):
        """Preload critical modules in background thread."""
        def preload_worker():
            """Background worker to preload modules."""
            try:
                # Preload heavy modules that will be used later
                import json
                import asyncio
                import concurrent.futures
                import urllib.parse
                import base64
                import hashlib
                
                # Preload PyQt6 modules
                from PyQt6.QtCore import QTimer, QThread
                from PyQt6.QtWidgets import QApplication
                from PyQt6.QtGui import QPixmap, QIcon
                
                logger.debug("Preloaded critical modules in background")
                
            except Exception as e:
                logger.debug(f"Module preloading completed with some errors: {e}")
        
        try:
            # Start preloading in background thread
            preload_thread = threading.Thread(target=preload_worker, daemon=True)
            preload_thread.start()
            
            self.optimizations_applied.append("Module preloading")
            
        except Exception as e:
            logger.warning(f"Failed to start module preloading: {e}")
    
    def _optimize_file_system_access(self):
        """Optimize file system access patterns."""
        try:
            # Set process priority for better I/O performance (Windows)
            if sys.platform == "win32":
                try:
                    import psutil
                    process = psutil.Process()
                    process.nice(psutil.HIGH_PRIORITY_CLASS)
                    logger.debug("Set high priority for better I/O performance")
                except ImportError:
                    # psutil not available, use Windows API
                    try:
                        import ctypes
                        from ctypes import wintypes
                        
                        # Set high priority class
                        kernel32 = ctypes.windll.kernel32
                        handle = kernel32.GetCurrentProcess()
                        kernel32.SetPriorityClass(handle, 0x00000080)  # HIGH_PRIORITY_CLASS
                        
                        logger.debug("Set high priority using Windows API")
                    except Exception:
                        pass  # Silently fail if we can't set priority
            
            self.optimizations_applied.append("File system optimization")
            
        except Exception as e:
            logger.warning(f"Failed to apply file system optimizations: {e}")
    
    def optimize_ui_startup(self, app):
        """Optimize UI startup performance."""
        if not self.is_frozen:
            return
        
        try:
            # Optimize Qt application settings
            app.setAttribute(app.ApplicationAttribute.AA_DontCreateNativeWidgetSiblings, True)
            app.setAttribute(app.ApplicationAttribute.AA_NativeWindows, False)
            app.setAttribute(app.ApplicationAttribute.AA_DontUseNativeMenuBar, True)
            
            # Enable high DPI scaling
            app.setAttribute(app.ApplicationAttribute.AA_EnableHighDpiScaling, True)
            app.setAttribute(app.ApplicationAttribute.AA_UseHighDpiPixmaps, True)
            
            logger.debug("Applied UI startup optimizations")
            
        except Exception as e:
            logger.warning(f"Failed to apply UI optimizations: {e}")
    
    def create_performance_monitor(self):
        """Create a performance monitor for debugging."""
        if not logger.isEnabledFor(logging.DEBUG):
            return None
        
        class PerformanceMonitor:
            def __init__(self):
                self.start_time = time.time()
                self.checkpoints = []
            
            def checkpoint(self, name):
                current_time = time.time()
                elapsed = current_time - self.start_time
                self.checkpoints.append((name, elapsed))
                logger.debug(f"Performance checkpoint '{name}': {elapsed:.3f}s")
            
            def summary(self):
                total_time = time.time() - self.start_time
                logger.info(f"Startup performance summary (total: {total_time:.3f}s):")
                for name, elapsed in self.checkpoints:
                    percentage = (elapsed / total_time) * 100
                    logger.info(f"  {name}: {elapsed:.3f}s ({percentage:.1f}%)")
        
        return PerformanceMonitor()

# Global optimizer instance
_optimizer = None

def get_optimizer():
    """Get the global startup optimizer instance."""
    global _optimizer
    if _optimizer is None:
        _optimizer = StartupOptimizer()
    return _optimizer

def apply_startup_optimizations():
    """Apply all startup optimizations."""
    optimizer = get_optimizer()
    optimizer.apply_all_optimizations()
    return optimizer

def optimize_ui_startup(app):
    """Optimize UI startup for the given QApplication."""
    optimizer = get_optimizer()
    optimizer.optimize_ui_startup(app)

def create_performance_monitor():
    """Create a performance monitor for debugging startup times."""
    optimizer = get_optimizer()
    return optimizer.create_performance_monitor()

# Auto-apply optimizations when module is imported in frozen mode
if getattr(sys, 'frozen', False):
    # Only auto-apply basic optimizations
    try:
        _auto_optimizer = StartupOptimizer()
        _auto_optimizer._optimize_python_settings()
        _auto_optimizer._optimize_memory_usage()
    except Exception:
        pass  # Silently fail to avoid breaking startup